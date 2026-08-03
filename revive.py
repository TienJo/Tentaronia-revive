import os
import json
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta

# ==========================================
# 1. 多重備援行情數據引擎
# ==========================================
class MultiSourceMarketData:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://quote.eastmoney.com/"
        }
        self.fund_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fundf10.eastmoney.com/"
        }

    def fetch_ohlc(self, symbol: str) -> tuple[pd.DataFrame, str]:
        clean_code = symbol.split('.')[0].upper()

        try:
            df = self._fetch_eastmoney(symbol, clean_code)
            if not df.empty and len(df) >= 30:
                return df, "東方財富 (EastMoney)"
        except Exception:
            pass

        if clean_code.isdigit() and len(clean_code) == 6:
            try:
                df = self._fetch_eastmoney_fund(clean_code)
                if not df.empty and len(df) >= 30:
                    return df, "天天基金 (Tiantian Fund)"
            except Exception:
                pass

        try:
            df = self._fetch_tencent(symbol, clean_code)
            if not df.empty and len(df) >= 30:
                return df, "騰訊財經 (Tencent)"
        except Exception:
            pass

        try:
            df = self._fetch_sina(symbol, clean_code)
            if not df.empty and len(df) >= 30:
                return df, "新浪財經 (Sina)"
        except Exception:
            pass

        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            try:
                df = self._fetch_twse_official(clean_code)
                if not df.empty and len(df) >= 30:
                    return df, "台灣證交所官方 (TWSE)"
            except Exception:
                pass

        try:
            df = self._fetch_yfinance(symbol)
            if not df.empty and len(df) >= 30:
                return df, "yfinance (備用)"
        except Exception:
            pass

        raise ValueError(f"無法獲取 {symbol} 行情數據，請確認代碼是否正確。")

    def _fetch_eastmoney_fund(self, fund_code: str) -> pd.DataFrame:
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        params = {"fundCode": fund_code, "pageIndex": 1, "pageSize": 150, "startDate": "", "endDate": ""}
        resp = requests.get(url, params=params, headers=self.fund_headers, timeout=5)
        data = resp.json()

        if not data or "Data" not in data or not data["Data"] or "LSJZList" not in data["Data"]:
            return pd.DataFrame()

        raw_list = data["Data"]["LSJZList"]
        records = []
        for item in raw_list:
            if item.get("DWJZ"):
                jz = float(item["DWJZ"])
                records.append({"Date": item["FSRQ"], "Open": jz, "High": jz, "Low": jz, "Close": jz, "Volume": 10000.0})

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df['Date'])
        df.sort_values('Date', inplace=True)
        df.set_index('Date', inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_eastmoney(self, symbol: str, clean_code: str) -> pd.DataFrame:
        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            secid = f"116.{clean_code}"
        elif clean_code.startswith(("60", "688", "900", "51", "56", "58")) or symbol.endswith(".SS"):
            secid = f"1.{clean_code}"
        elif clean_code.startswith(("00", "01", "300", "200", "15", "16", "18")) or symbol.endswith(".SZ"):
            secid = f"0.{clean_code}"
        else:
            secid = f"0.{clean_code}"

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b", "klt": "101", "fqt": "1", "end": "20500101", "lmt": "150", "secid": secid
        }
        resp = requests.get(url, params=params, headers=self.headers, timeout=5)
        data = resp.json()
        
        if not data or "data" not in data or not data["data"] or "klines" not in data["data"]:
            return pd.DataFrame()

        raw_klines = data["data"]["klines"]
        records = []
        for line in raw_klines:
            p = line.split(",")
            records.append({"Date": p[0], "Open": float(p[1]), "Close": float(p[2]), "High": float(p[3]), "Low": float(p[4]), "Volume": float(p[5])})
        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_tencent(self, symbol: str, clean_code: str) -> pd.DataFrame:
        if clean_code.startswith(("60", "688", "900", "51", "56", "58")) or symbol.endswith(".SS"):
            tc_symbol = f"sh{clean_code}"
        elif clean_code.startswith(("00", "01", "300", "200", "15", "16", "18")) or symbol.endswith(".SZ"):
            tc_symbol = f"sz{clean_code}"
        else:
            tc_symbol = f"r_tw{clean_code}"

        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc_symbol},day,,,160,qfq"
        resp = requests.get(url, headers=self.headers, timeout=5)
        data = resp.json()
        
        if not data or "data" not in data or tc_symbol not in data["data"]:
            return pd.DataFrame()
            
        stock_data = data["data"][tc_symbol]
        kline_key = "qfqday" if "qfqday" in stock_data else ("day" if "day" in stock_data else None)
        if not kline_key or not stock_data[kline_key]:
            return pd.DataFrame()

        records = []
        for item in stock_data[kline_key]:
            records.append({"Date": item[0], "Open": float(item[1]), "Close": float(item[2]), "High": float(item[3]), "Low": float(item[4]), "Volume": float(item[5])})
        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_sina(self, symbol: str, clean_code: str) -> pd.DataFrame:
        if clean_code.startswith(("60", "688", "900", "51", "56", "58")) or symbol.endswith(".SS"):
            sina_symbol = f"sh{clean_code}"
        elif clean_code.startswith(("00", "01", "300", "200", "15", "16", "18")) or symbol.endswith(".SZ"):
            sina_symbol = f"sz{clean_code}"
        else:
            return pd.DataFrame()

        url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_{sina_symbol}=/CN_MarketDataService.getKLineData?symbol={sina_symbol}&scale=240&ma=no&datalen=150"
        resp = requests.get(url, headers=self.headers, timeout=5)
        text = resp.text
        
        if "(" in text and ")" in text:
            json_str = text[text.find("(")+1 : text.rfind(")")]
            data = json.loads(json_str)
            if data and isinstance(data, list):
                records = []
                for item in data:
                    records.append({"Date": item["day"], "Open": float(item["open"]), "Close": float(item["close"]), "High": float(item["high"]), "Low": float(item["low"]), "Volume": float(item["volume"])})
                df = pd.DataFrame(records)
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        return pd.DataFrame()

    def _fetch_twse_official(self, clean_code: str) -> pd.DataFrame:
        records = []
        today = datetime.now()
        for i in range(4):
            date_str = (today - timedelta(days=i*28)).strftime("%Y%m01")
            url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={date_str}&stockNo={clean_code}&response=json"
            resp = requests.get(url, headers=self.headers, timeout=4)
            data = resp.json()
            if "data" in data:
                for row in data["data"]:
                    parts = row[0].split('/')
                    year = int(parts[0]) + 1911
                    records.append({
                        "Date": f"{year}-{parts[1]}-{parts[2]}",
                        "Open": float(row[3].replace(',', '')), "High": float(row[4].replace(',', '')),
                        "Low": float(row[5].replace(',', '')), "Close": float(row[6].replace(',', '')),
                        "Volume": float(row[1].replace(',', ''))
                    })
            time.sleep(0.15)
        df = pd.DataFrame(records).drop_duplicates(subset=['Date'])
        df['Date'] = pd.to_datetime(df['Date'])
        df.sort_values('Date', inplace=True)
        df.set_index('Date', inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_yfinance(self, symbol: str) -> pd.DataFrame:
        clean_code = symbol.split('.')[0].upper()
        if clean_code.isdigit() and not (symbol.endswith(".TW") or symbol.endswith(".TWO")):
            if clean_code.startswith(("60", "688", "51", "56", "58")):
                yf_symbol = f"{clean_code}.SS"
            elif clean_code.startswith(("00", "01", "300", "15", "16", "18")):
                yf_symbol = f"{clean_code}.SZ"
            else:
                yf_symbol = symbol
        else:
            yf_symbol = symbol

        for attempt in range(3):
            try:
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period="1y")
                if not df.empty and len(df) >= 30:
                    df = df.reset_index()
                    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                    df.set_index('Date', inplace=True)
                    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            except Exception:
                pass
            time.sleep(1.0 * (attempt + 1))
        return pd.DataFrame()


# ==========================================
# 2. 策略與指標計算引擎
# ==========================================
class TradingStrategyEngine:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA10'] = df['Close'].rolling(10).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['MA10_Vol'] = df['Volume'].rolling(10).mean()

        candle_range = df['High'] - df['Low']
        df['Candle_Body_Ratio'] = np.where(candle_range > 0, (df['Close'] - df['Open']) / candle_range, 0.0)
        df['Bias_MA20'] = (df['Close'] - df['MA20']) / df['MA20'] * 100.0
        df['MA60_Slope'] = df['MA60'] - df['MA60'].shift(3)

        df['TR0'] = df['High'] - df['Low']
        df['TR1'] = (df['High'] - df['Close'].shift(1)).abs()
        df['TR2'] = (df['Low'] - df['Close'].shift(1)).abs()
        df['TR'] = df[['TR0', 'TR1', 'TR2']].max(axis=1)
        df['ATR14'] = df['TR'].ewm(alpha=1/14, adjust=False).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI14'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

        df['High_20'] = df['High'].shift(1).rolling(20).max()
        df['Low_10'] = df['Low'].shift(1).rolling(10).min()
        df['Low_20'] = df['Low'].shift(1).rolling(20).min()

        # 溫度 T 算力公式
        chg_20 = df['Close'].pct_change(20) * 100
        min_20_chg = chg_20.rolling(60).min()
        max_20_chg = chg_20.rolling(60).max()
        f1_chg = np.where(max_20_chg > min_20_chg, (chg_20 - min_20_chg) / (max_20_chg - min_20_chg) * 100, 50.0)

        f2_pos = np.where(df['High_20'] > df['Low_20'], (df['Close'] - df['Low_20']) / (df['High_20'] - df['Low_20']) * 100, 50.0)

        ma_score = (np.where(df['Close'] > df['MA5'], 25, 0) + 
                    np.where(df['Close'] > df['MA10'], 25, 0) + 
                    np.where(df['Close'] > df['MA20'], 25, 0) + 
                    np.where(df['Close'] > df['MA60'], 25, 0))

        f4_rsi = df['RSI14'].fillna(50.0)

        hist = df['MACD_Hist']
        min_hist = hist.rolling(60).min()
        max_hist = hist.rolling(60).max()
        f5_macd = np.where(max_hist > min_hist, (hist - min_hist) / (max_hist - min_hist) * 100, 50.0)

        df['Temperature'] = (0.24 * f1_chg + 0.22 * f2_pos + 0.22 * ma_score + 0.18 * f4_rsi + 0.14 * f5_macd).clip(0, 100)

        return df

    @staticmethod
    def evaluate_pre_trade_advice(df: pd.DataFrame, stock_info: dict, pos_summary: dict, target_capital: float) -> tuple[dict, list[dict]]:
        df_ind = TradingStrategyEngine.calculate_indicators(df)
        today = df_ind.iloc[-1]
        yesterday = df_ind.iloc[-2]

        price = float(today['Close'])
        prev_close = float(yesterday['Close'])
        high = float(today['High'])
        low = float(today['Low'])
        volume = float(today['Volume'])
        ma5, ma10, ma20, ma60 = float(today['MA5']), float(today['MA10']), float(today['MA20']), float(today['MA60'])
        ma10_vol_prev = float(yesterday['MA10_Vol'])
        bias_ma20 = float(today['Bias_MA20'])
        ma60_upward = float(today['MA60_Slope']) > 0
        atr14 = float(today['ATR14'])
        rsi14 = float(today['RSI14'])
        temp = float(today['Temperature'])
        high_20 = float(today['High_20']) if not np.isnan(today['High_20']) else float(today['High'])
        low_10 = float(today['Low_10']) if not np.isnan(today['Low_10']) else float(today['Low'])

        vol_ratio = volume / ma10_vol_prev if ma10_vol_prev > 0 else 0.0

        touch_ma20 = (low <= ma20 * 1.015) and (price >= ma20 * 0.985)
        retest_support = touch_ma20 and (vol_ratio < 1.0) and (price > float(today['Open']))

        is_bull_wave = ma60_upward and (price >= high_20)

        # 當日漲跌幅與金額計算
        daily_change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        daily_pnl = (price - prev_close) * pos_summary['total_shares'] if pos_summary['total_shares'] > 0 else 0.0

        metrics = {
            "Close": price, "Prev_Close": prev_close, "Daily_Change_Pct": daily_change_pct, "Daily_PnL": daily_pnl,
            "High": high, "MA5": ma5, "MA10": ma10, "MA20": ma20, "MA60": ma60,
            "MA60_Trend": "向上走牛 ↗️" if ma60_upward else "走平/向下 ↘️",
            "Vol_Ratio": vol_ratio, "Bias_MA20": bias_ma20, "ATR14": atr14, "RSI14": rsi14,
            "Temperature": temp, "High_20": high_20, "Low_10": low_10, "Is_Bull_Wave": is_bull_wave
        }

        tranches_held = pos_summary['tranches_held']
        unrealized_pnl = pos_summary['unrealized_pnl']
        avg_cost = pos_summary['avg_cost']
        tranche_budget = pos_summary['tranche_budget']
        
        target_shares_1t = int(tranche_budget / price) if price > 0 else 0

        if tranches_held > 0 and price < avg_cost:
            loss_pct = ((avg_cost - price) / avg_cost) * 100.0

            if price < ma20 and price < low_10:
                sell_shares = int(pos_summary['total_shares'] * 0.3)
                return metrics, [{"type": "error", "action_code": "STOP_LOSS_10", "title": "🚨 觸發止損減碼：MA20 以下跌破近 10 日最低點", "desc": f"當前淨值 ({price:.4f}) 於 MA20 下方跌破近 10 日最低點 ({low_10:.4f})！建議於 15:00 前減碼 30% 份額 (約 {sell_shares:,} 份) 規避風險。"}]

            if price < ma20:
                if temp <= 15.0:
                    return metrics, [{"type": "success", "action_code": "BUY_T1", "title": f"❄️ 【市場極度冰點 (溫度 {temp:.1f}度)】超跌左側低吸", "desc": f"當前板塊/標的溫度降至 {temp:.1f} 度極度冰點！為高勝率築底區，建議於 15:00 前申購 1 層 (~${tranche_budget:,.0f} 元，約 {target_shares_1t:,} 份) 攤平。"}]
                else:
                    return metrics, [{"type": "warning", "action_code": "LOCK_BUY", "title": f"🛡️ 防守觀望狀態 (當前溫度 {temp:.1f}度)：淨值未站回 MA20 前禁止申購", "desc": f"淨值 ({price:.4f}) 低於 MA20 月線 ({ma20:.4f})。在重新站回 MA20 之前，禁止進行任何申購。"}]

            if is_bull_wave or (temp >= 70.0 and price >= ma20):
                if tranches_held < 8.0:
                    return metrics, [{"type": "success", "action_code": "BUY_T1", "title": f"🔥 【過渡至牛市主浪 (溫度 {temp:.1f}度)】：終止解套贖回！加碼 1 層", "desc": f"標的進入高溫主升浪區 ({temp:.1f} 度)！波段強勢開啟，正式終止解套贖回，建議申購 1 層 (~${tranche_budget:,.0f} 元，約 {target_shares_1t:,} 份) 追擊獲利。"}]
                else:
                    return metrics, [{"type": "success", "action_code": "HOLD", "title": f"🔥 【過渡至牛市主浪 (溫度 {temp:.1f}度)】：解除贖回，重倉抱緊放大收益", "desc": f"當前處於強勢主升浪，解除解套贖回指令，維持高倉位抱緊，享受主升浪收益。"}]

            if loss_pct <= 5.0:
                sell_shares = int(pos_summary['total_shares'] * 0.3)
                return metrics, [{"type": "success", "action_code": "REDUCE_RECOVER", "title": "🎯 階梯解套贖回：虧損收窄至 5% 內，贖回 30%", "desc": f"虧損已收窄至 {loss_pct:.1f}%！建議於 15:00 前贖回 30% 份額 (約 {sell_shares:,} 份) 回籠現金。"}]
            elif loss_pct <= 10.0 and bias_ma20 > 4.0:
                sell_shares = int(pos_summary['total_shares'] * 0.2)
                return metrics, [{"type": "warning", "action_code": "REDUCE_RECOVER", "title": "📌 階梯解套贖回：反彈觸及壓力區，贖回 20%", "desc": f"虧損收窄至 {loss_pct:.1f}%，建議於 15:00 前贖回 20% 份額 (約 {sell_shares:,} 份)。"}]

            if retest_support and tranches_held < 9.5:
                return metrics, [{"type": "success", "action_code": "BUY_T1", "title": "🔄 右側加碼申購：站回 MA20 後縮量回踩獲得支撐", "desc": f"企穩於 MA20 上方並縮量回踩！可於 15:00 前申購 1 層資金 (~${tranche_budget:,.0f} 元，約 {target_shares_1t:,} 份) 拉低成本。"}]

            return metrics, [{"type": "info", "action_code": "HOLD", "title": f"🟢 溫和反彈中 (當前溫度 {temp:.1f}度)：站穩 MA20，持基靜待解套", "desc": f"目前套牢虧損 {loss_pct:.1f}%，無贖回或申購訊號，15:00 前保持觀望。"}]

        elif tranches_held > 0 and price >= avg_cost:
            if temp >= 85.0 or bias_ma20 > 12.0:
                sell_shares = int(pos_summary['total_shares'] * 0.5)
                return metrics, [{"type": "warning", "action_code": "REDUCE_50", "title": f"🔥 完全解套獲利：極度過熱 (溫度 {temp:.1f}度)，贖回 50% 落袋為安", "desc": f"已實現獲利！標的進入極度過熱區，建議贖回一半份額 (約 {sell_shares:,} 份) 鎖定勝果。"}]
            return metrics, [{"type": "info", "action_code": "HOLD", "title": f"🎉 已完全解套盈利 (溫度 {temp:.1f}度)！牛市主浪持基續抱", "desc": "淨值已超越成本線，維持持有狀態放大獲利。"}]

        else:
            if retest_support and price >= ma20:
                return metrics, [{"type": "success", "action_code": "BUY_T1", "title": "🎯 策略建議：15:00 前可申購 1 層底倉", "desc": f"建議申購 1 層資金 (~${tranche_budget:,.0f} 元，約 {target_shares_1t:,} 份)。"}]
            return metrics, [{"type": "info", "action_code": "HOLD", "title": "💤 觀望階段", "desc": "未站回 MA20 或無明確買點，保持觀望。"}]

    @staticmethod
    def audit_post_trade(action_type: str, trade_price: float, trade_shares: int, pre_signals: list[dict], pre_pos: dict, metrics: dict) -> tuple[list[dict], list[dict]]:
        audit_items = []
        watchlist_items = []

        advised_codes = [s.get('action_code') for s in pre_signals]

        if action_type in ["BUY", "ADD"]:
            if any(code in ['BUY_T1'] for code in advised_codes):
                audit_items.append({"level": "success", "title": "✅ 依策略建議申購加碼", "detail": "成功在冰點低吸申購或主浪開啟時加碼。"})
            elif 'LOCK_BUY' in advised_codes:
                audit_items.append({"level": "error", "title": "❌ 嚴重違反紀律：MA20 以下禁止任何申購加碼！", "detail": "淨值未站回 MA20 前加碼屬於逆勢攤平，大大增加了套牢風險。"})
            else:
                audit_items.append({"level": "warning", "title": "⚠️ 非策略性追高/盲目申購", "detail": "當前無確定性買點，盲目申購可能加重套牢負擔。"})

        elif action_type == "SELL":
            if any(code in ['STOP_LOSS_10', 'REDUCE_RECOVER', 'REDUCE_50'] for code in advised_codes):
                audit_items.append({"level": "success", "title": "💯 果斷執行止損/階梯解套贖回", "detail": "成功降減風險或回收現金！"})
            else:
                audit_items.append({"level": "info", "title": "ℹ️ 自主贖回離場", "detail": "您選擇主動贖回部分份額回收現金。"})

        elif action_type == "NONE":
            if 'STOP_LOSS_10' in advised_codes:
                audit_items.append({"level": "error", "title": "🚨 嚴重違規：未執行破近 10 日新低之減碼指令！", "detail": "已觸發 MA20 以下破底減碼條件，未賣出部位將承擔高下行風險。"})
            else:
                audit_items.append({"level": "success", "title": "💯 策略執行合規", "detail": "當日無操作，持基觀望完全符合策略指引。"})

        ma20 = metrics['MA20']
        low_10 = metrics['Low_10']
        temp = metrics['Temperature']

        watchlist_items.append({"title": "🌡️ 即時標的溫度", "value": f"{temp:.1f} 度", "desc": "極度冰點 <15度 (高勝率低吸) | 溫和區 20~60度 (震盪解套) | 高溫區 >70度 (牛市主浪/贖回)"})
        watchlist_items.append({"title": "🛡️ MA20 禁買防守分界線", "value": f"{ma20:.4f}", "desc": f"淨值於 {ma20:.4f} 以下強行進入『禁買防守狀態』，站回前禁止申購。"})
        watchlist_items.append({"title": "🚨 破底減碼警戒價 (近 10 日最低點)", "value": f"{low_10:.4f}", "desc": f"若淨值在 MA20 以下跌破 {low_10:.4f}，須強制減碼 30% 避險。"})

        return audit_items, watchlist_items


# ==========================================
# 3. 本地 JSON 數據庫管理者
# ==========================================
DB_FILE = "portfolio_data.json"

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def load_db():
    default_db = {
        "stocks": {
            "513380": {
                "symbol": "513380", "name": "恆生科技ETF廣發",
                "target_capital": 300000.0,
                "trades": [
                    {"date": "2026-07-25", "type": "BUY", "price": 0.5850, "shares": 53523, "note": "當前套牢部位校正"}
                ],
                "peak_price_since_entry": 0.0, "peak_unrealized_pnl": 0.0
            }
        }
    }

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "stocks" in data:
                for s_key, s_val in data["stocks"].items():
                    s_val.setdefault("target_capital", 500000.0)
                return data
            else:
                new_data = {"stocks": {}}
                for key, val in data.items():
                    if isinstance(val, dict):
                        new_data["stocks"][key] = {
                            "symbol": val.get("symbol", key),
                            "name": val.get("name", key),
                            "target_capital": 500000.0,
                            "trades": [],
                            "peak_price_since_entry": 0.0,
                            "peak_unrealized_pnl": 0.0
                        }
                save_db(new_data)
                return new_data
        except Exception:
            save_db(default_db)
            return default_db
    else:
        save_db(default_db)
        return default_db

def compute_position_summary(trades: list, current_price: float, target_capital: float) -> dict:
    tranche_budget = target_capital * 0.10
    total_shares = 0
    total_cost = 0.0
    realized_pnl = 0.0

    for t in trades:
        t_type = t['type']
        t_price = float(t['price'])
        t_shares = int(t['shares'])
        t_amount = t_price * t_shares

        if t_type == "BUY":
            total_shares += t_shares
            total_cost += t_amount
        elif t_type == "SELL":
            if total_shares > 0:
                avg_cost_before = total_cost / total_shares
                sold_cost = avg_cost_before * t_shares
                total_shares = max(0, total_shares - t_shares)
                total_cost = max(0.0, total_cost - sold_cost)
                realized_pnl += (t_amount - sold_cost)

    avg_cost = total_cost / total_shares if total_shares > 0 else 0.0
    unrealized_pnl = (current_price * total_shares - total_cost) if total_shares > 0 else 0.0
    tranches_held = round(total_cost / tranche_budget, 1) if tranche_budget > 0 else 0.0

    return {
        "total_shares": total_shares,
        "total_cost": total_cost,
        "avg_cost": avg_cost,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "tranches_held": tranches_held,
        "tranche_budget": tranche_budget
    }


# ==========================================
# 4. Streamlit 視覺化 GUI 主介面
# ==========================================
st.set_page_config(page_title="溫度解套與主浪助手 App", layout="wide", page_icon="📈")

if "db" not in st.session_state:
    st.session_state.db = load_db()

db = st.session_state.db
db.setdefault("stocks", {})

data_engine = MultiSourceMarketData()

# ----------------- 側邊欄設定 -----------------
st.sidebar.title("⚙️ 控制面板")

st.sidebar.subheader("📌 自選標的切換與管理")
active_stock = st.sidebar.selectbox("🔍 選擇當前操作標的", options=list(db["stocks"].keys()) if db.get("stocks") else [])

if active_stock and active_stock in db["stocks"]:
    curr_stock = db["stocks"][active_stock]
    st.sidebar.markdown("---")
    st.sidebar.subheader(f"💰 {curr_stock['name']} 獨立投資資本設定")
    
    target_cap = st.sidebar.number_input(
        f"該標的專屬總預算上限 (元)",
        min_value=10000.0, max_value=100000000.0,
        value=float(curr_stock.get("target_capital", 300000.0)), step=50000.0
    )
    if target_cap != curr_stock.get("target_capital"):
        curr_stock["target_capital"] = target_cap
        save_db(db)
        st.rerun()

    st.sidebar.caption(f"💡 該標的單層資金 (10%) = ${target_cap * 0.10:,.0f} 元")

    st.sidebar.markdown("---")
    with st.sidebar.expander("🛠️ 快速校正/初始化目前持倉", expanded=False):
        st.caption("輸入目前的持倉狀況，覆蓋歷史資料：")
        init_cost = st.number_input("目前持倉均價 (元)", min_value=0.0, value=float(curr_stock["trades"][0]["price"]) if curr_stock.get("trades") else 0.0, format="%.4f")
        init_shares = st.number_input("目前持倉總股數/份額", min_value=0, value=int(curr_stock["trades"][0]["shares"]) if curr_stock.get("trades") else 0, step=100)
        
        if st.button("💾 覆蓋為當前真實持倉"):
            if init_cost > 0 and init_shares > 0:
                curr_stock["trades"] = [{
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "BUY",
                    "price": init_cost,
                    "shares": init_shares,
                    "note": "初始化已有持倉/套牢部位"
                }]
                save_db(db)
                st.sidebar.success("✅ 持倉校正成功！")
                st.rerun()
            else:
                st.sidebar.error("請輸入大於 0 的均價與股數！")

st.sidebar.markdown("---")

with st.sidebar.expander("➕ 新增標的", expanded=False):
    new_sym = st.text_input("代碼 (台股 2330.TW / ETF 513380 / 基金 013396)", "").strip().upper()
    new_name = st.text_input("標的名稱 (選填，若空白將自動使用代碼)", "").strip()
    new_cap = st.number_input("為此標的設定獨立資本上限 (元)", min_value=10000.0, max_value=100000000.0, value=100000.0, step=50000.0)
    
    if st.button("確認新增"):
        if new_sym:
            final_name = new_name if new_name else new_sym
            if new_sym not in db["stocks"]:
                db["stocks"][new_sym] = {
                    "symbol": new_sym,
                    "name": final_name,
                    "target_capital": new_cap,
                    "trades": [],
                    "peak_price_since_entry": 0.0,
                    "peak_unrealized_pnl": 0.0
                }
                save_db(db)
                st.sidebar.success(f"✅ 已成功加入 {new_sym} ({final_name})")
                st.rerun()
            else:
                st.sidebar.warning(f"⚠️ {new_sym} 已存在於自選庫中！")
        else:
            st.sidebar.error("❌ 請輸入標的代碼！")

if db.get("stocks"):
    del_sym = st.sidebar.selectbox("🗑️ 刪除標的", options=list(db["stocks"].keys()))
    if st.sidebar.button("確認刪除標的"):
        del db["stocks"][del_sym]
        save_db(db)
        st.sidebar.success(f"已刪除 {del_sym}")
        st.rerun()

st.title("📈 場外基金解套與溫度過渡助手")

if not active_stock or active_stock not in db["stocks"]:
    st.info("請先在左側邊欄新增自選標的。")
    st.stop()

stock_info = db["stocks"][active_stock]
stock_target_capital = float(stock_info.get("target_capital", 300000.0))

tab1, tab2, tab3 = st.tabs(["📊 解套/主浪診斷與申贖對帳", "📐 關鍵技術指標與溫度詳情", "🔍 全自選庫一鍵掃描"])

with st.spinner(f"正在擷取 {stock_info['name']} 最新行情數據..."):
    try:
        df_kline, source_used = data_engine.fetch_ohlc(stock_info['symbol'])
        pos_summary = compute_position_summary(stock_info.get('trades', []), df_kline.iloc[-1]['Close'], stock_target_capital)
        metrics, pre_signals = TradingStrategyEngine.evaluate_pre_trade_advice(df_kline, stock_info, pos_summary, stock_target_capital)
    except Exception as e:
        st.error(f"行情擷取失敗: {e}")
        st.stop()

# Tab 1: 主介面
with tab1:
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.subheader(f"{stock_info['name']} ({stock_info['symbol']})")
    with col_t2:
        st.caption(f"🟢 行情來源: {source_used}")

    # 改為 7 個指標欄位，新增「當日即時損益」
    m0, m1, m2, m3, m4, m5, m6 = st.columns(7)
    m0.metric("即時標的溫度 T", f"{metrics['Temperature']:.1f} 度", delta="極度冰點" if metrics['Temperature'] <= 15 else "高溫主浪" if metrics['Temperature'] >= 70 else "溫和區")
    m1.metric("當前最新淨值/股價", f"{metrics['Close']:.4f}" if metrics['Close'] < 10 else f"{metrics['Close']:.2f}")
    
    # 🆕 新增：當日即時損益欄位
    daily_pnl_str = f"${metrics['Daily_PnL']:,.0f}" if pos_summary['total_shares'] > 0 else "$0"
    m2.metric("當日即時損益", daily_pnl_str, delta=f"{metrics['Daily_Change_Pct']:+.2f}%")

    m3.metric("持有資金層數", f"{pos_summary['tranches_held']:.1f} / 10 層")
    m4.metric("持倉平均成本", f"{pos_summary['avg_cost']:.4f}" if pos_summary['avg_cost'] < 10 else f"{pos_summary['avg_cost']:.2f}" if pos_summary['total_shares'] > 0 else "未開倉")
    u_pnl_pct = (pos_summary['unrealized_pnl'] / pos_summary['total_cost'] * 100.0) if pos_summary['total_cost'] > 0 else 0.0
    m5.metric("即時未實現總損益", f"${pos_summary['unrealized_pnl']:,.0f}", delta=f"{u_pnl_pct:.2f}%" if pos_summary['total_shares'] > 0 else "0%")
    m6.metric("持有總份額/股數", f"{pos_summary['total_shares']:,}")

    if pos_summary['total_shares'] > 0 and pos_summary['avg_cost'] > metrics['Close']:
        gap_pct = ((pos_summary['avg_cost'] - metrics['Close']) / metrics['Close']) * 100.0
        st.warning(f"📉 **狀態提醒**：目前部位處於套牢狀態（虧損 {abs(u_pnl_pct):.2f}%），距離完全回本仍需上漲 **{gap_pct:.2f}%**。若未來突破 20 日高點 ({metrics['High_20']:.4f}) 且溫度 > 70度，系統將自動啟動『牛市主浪過渡』！")

    st.markdown("---")

    st.markdown("### 🎯 第一次分析：當日 15:00 前操作建議")
    for sig in pre_signals:
        if sig['type'] == 'success':
            st.success(f"**{sig['title']}**\n\n{sig['desc']}")
        elif sig['type'] == 'warning':
            st.warning(f"**{sig['title']}**\n\n{sig['desc']}")
        elif sig['type'] == 'error':
            st.error(f"**{sig['title']}**\n\n{sig['desc']}")
        else:
            st.info(f"**{sig['title']}**\n\n{sig['desc']}")

    st.markdown("---")

    st.markdown("### ✏️ 紀錄今日 15:00 前實際執行之申購/贖回交易")
    with st.form("daily_trade_form"):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            action_choice = st.selectbox("當日操作類型", ["今日無操作 / 續抱", "申購 / 低吸加碼", "贖回 / 分批離場"])
        with col_f2:
            trade_price = st.number_input("預估/成交淨值", min_value=0.0, value=float(metrics['Close']), format="%.4f")
        with col_f3:
            trade_shares = st.number_input("成交數量 (份額)", min_value=0, value=1000, step=100)

        trade_note = st.text_input("交易備註 (選填)", "")
        submit_trade = st.form_submit_button("💾 記錄交易並進行第二次合規分析", type="primary")

        stock_action_key = f"last_action_{active_stock}"
        stock_price_key = f"last_price_{active_stock}"
        stock_shares_key = f"last_shares_{active_stock}"

        if submit_trade:
            if action_choice != "今日無操作 / 續抱" and trade_shares > 0:
                t_type = "BUY" if "申購" in action_choice or "加碼" in action_choice else "SELL"
                new_trade = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": t_type,
                    "price": trade_price,
                    "shares": trade_shares,
                    "note": trade_note
                }
                stock_info.setdefault("trades", []).append(new_trade)
                save_db(db)
                st.session_state[stock_action_key] = t_type
                st.session_state[stock_price_key] = trade_price
                st.session_state[stock_shares_key] = trade_shares
                st.success("✅ 交易紀錄已儲存！")
            else:
                st.session_state[stock_action_key] = "NONE"
                st.session_state[stock_price_key] = metrics['Close']
                st.session_state[stock_shares_key] = 0
                st.info("已確認今日無操作。")
            st.rerun()

    st.markdown("### 🔍 第二次分析：策略執行度合規檢討與短期注意事項")
    
    stock_action_key = f"last_action_{active_stock}"
    stock_price_key = f"last_price_{active_stock}"
    stock_shares_key = f"last_shares_{active_stock}"

    last_act = st.session_state.get(stock_action_key, "NONE")
    last_p = st.session_state.get(stock_price_key, metrics['Close'])
    last_s = st.session_state.get(stock_shares_key, 0)

    trades_list = stock_info.get("trades", [])
    if last_act != "NONE" and trades_list:
        trades_before = trades_list[:-1]
        pos_summary_before = compute_position_summary(trades_before, metrics['Close'], stock_target_capital)
        _, pre_signals_before = TradingStrategyEngine.evaluate_pre_trade_advice(df_kline, stock_info, pos_summary_before, stock_target_capital)
    else:
        pos_summary_before = pos_summary
        pre_signals_before = pre_signals

    audit_results, watchlist_results = TradingStrategyEngine.audit_post_trade(
        last_act, last_p, last_s, pre_signals_before, pos_summary_before, metrics
    )

    c_audit, c_watch = st.columns([1, 1])

    with c_audit:
        st.markdown("#### 💯 策略執行度與紀律診斷")
        for item in audit_results:
            if item['level'] == 'success':
                st.success(f"**{item['title']}**\n\n{item['detail']}")
            elif item['level'] == 'warning':
                st.warning(f"**{item['title']}**\n\n{item['detail']}")
            else:
                st.error(f"**{item['title']}**\n\n{item['detail']}")

    with c_watch:
        st.markdown("#### 📌 短期內應注意事項 (明日重點價位)")
        for item in watchlist_results:
            st.info(f"**{item['title']}**: `{item['value']}`\n\n↳ {item['desc']}")

    st.markdown("---")
    st.markdown("### 📜 歷史交易紀錄對帳單與 Note 二次編輯")
    
    trades_data = stock_info.get("trades", [])
    if trades_data:
        trade_df = pd.DataFrame(trades_data)
        trade_df['金額'] = trade_df['price'] * trade_df['shares']
        trade_df['類型'] = trade_df['type'].map({"BUY": "申購/加碼", "SELL": "贖回/離場"})
        
        st.dataframe(trade_df[['date', '類型', 'price', 'shares', '金額', 'note']], use_container_width=True)

        with st.expander("✏️ 編輯已送出交易紀錄的 Note 備註", expanded=False):
            trade_options = [f"第 {idx+1} 筆 - {t['date']} [{t['type']}] {t['shares']}份 @ {t['price']}元" for idx, t in enumerate(trades_data)]
            selected_trade_idx = st.selectbox("選擇要編輯的交易紀錄", options=range(len(trade_options)), format_func=lambda x: trade_options[x])
            
            curr_note = trades_data[selected_trade_idx].get("note", "")
            new_note_val = st.text_input("修改 Note 內容", value=curr_note)
            
            if st.button("💾 更新此筆 Note 備註"):
                trades_data[selected_trade_idx]["note"] = new_note_val
                save_db(db)
                st.success("✅ 備註已成功更新！")
                st.rerun()

        if st.button("🗑️ 清空該標的所有歷史交易紀錄"):
            stock_info["trades"] = []
            stock_info["peak_price_since_entry"] = 0.0
            stock_info["peak_unrealized_pnl"] = 0.0
            save_db(db)
            st.success("交易紀錄已重置！")
            st.rerun()
    else:
        st.caption("暫無歷史交易紀錄。請透過左側欄『快速校正/初始化目前持倉』來建立套牢持倉。")

# Tab 2: 指標詳情
with tab2:
    st.markdown("### 📐 當日技術指標與溫度權重拆解詳情")
    ind_df = pd.DataFrame([
        {"指標項目": "🔥 板塊/標的溫度 T", "當前數值": f"{metrics['Temperature']:.1f} 度"},
        {"指標項目": "📈 當日漲跌幅", "當前數值": f"{metrics['Daily_Change_Pct']:+.2f}%"},
        {"指標項目": "💵 當日即時損益", "當前數值": f"${metrics['Daily_PnL']:,.0f}"},
        {"指標項目": "MA5 五日均線", "當前數值": f"{metrics['MA5']:.4f}"},
        {"指標項目": "MA10 十日均線", "當前數值": f"{metrics['MA10']:.4f}"},
        {"指標項目": "MA20 月線 (禁買防守分界線)", "當前數值": f"{metrics['MA20']:.4f}"},
        {"指標項目": "MA60 季線 (生命線趨勢)", "當前數值": f"{metrics['MA60']:.4f} ({metrics['MA60_Trend']})"},
        {"指標項目": "近 10 日最低淨值 (破底止損價)", "當前數值": f"{metrics['Low_10']:.4f}"},
        {"指標項目": "近 20 日最高淨值 (牛市突破價)", "當前數值": f"{metrics['High_20']:.4f}"},
        {"指標項目": "RSI 14 (相對強弱)", "當前數值": f"{metrics['RSI14']:.2f}"},
    ])
    st.dataframe(ind_df, use_container_width=True, hide_index=True)

# Tab 3: 全自選掃描
with tab3:
    st.markdown("### 🔍 每日全自選場外標的一鍵解套/溫度掃描")
    if st.button("🚀 開始全自動掃描", type="primary"):
        results = []
        progress_bar = st.progress(0)
        stocks_dict = db.get("stocks", {})
        for idx, (sym, s_data) in enumerate(stocks_dict.items()):
            try:
                s_cap = float(s_data.get("target_capital", 300000.0))
                df_s, src = data_engine.fetch_ohlc(sym)
                p_sum = compute_position_summary(s_data.get('trades', []), df_s.iloc[-1]['Close'], s_cap)
                m, sigs = TradingStrategyEngine.evaluate_pre_trade_advice(df_s, s_data, p_sum, s_cap)
                sig_summary = " | ".join([s['title'] for s in sigs])
                results.append({
                    "代號": sym, "名稱": s_data['name'], 
                    "即時溫度 T": f"{m['Temperature']:.1f}度",
                    "最新淨值": f"{m['Close']:.4f}" if m['Close'] < 10 else f"{m['Close']:.2f}",
                    "當日損益": f"${m['Daily_PnL']:,.0f} ({m['Daily_Change_Pct']:+.2f}%)",
                    "持有層數": f"{p_sum['tranches_held']:.1f}層",
                    "RSI 14": f"{m['RSI14']:.1f}",
                    "10日低點": f"{m['Low_10']:.4f}" if m['Low_10'] < 10 else f"{m['Low_10']:.2f}",
                    "當日解套/主浪指引": sig_summary,
                    "數據源": src
                })
            except Exception as ex:
                results.append({"代號": sym, "名稱": s_data['name'], "當日解套/主浪指引": f"抓取失敗: {ex}"})
            progress_bar.progress((idx + 1) / len(stocks_dict))

        res_df = pd.DataFrame(results)
        st.dataframe(res_df, use_container_width=True, hide_index=True)
