import logging
import numpy as np
import pandas as pd
from typing import Dict, List

logger = logging.getLogger(__name__)

# Sector mapping for major stocks
STOCK_SECTOR_MAP = {
    # Technology
    "NVDA": "Technology", "AAPL": "Technology", "GOOGL": "Technology", "MSFT": "Technology",
    "META": "Technology", "AMZN": "Technology", "NFLX": "Technology", "INTC": "Technology",
    "AMD": "Technology", "ADBE": "Technology", "CRM": "Technology", "NOW": "Technology",
    "SNOW": "Technology", "DDOG": "Technology", "NET": "Technology", "OKTA": "Technology",
    "DASH": "Technology", "CRWD": "Technology", "PANW": "Technology", "ANET": "Technology",
    "COIN": "Technology", "RBLX": "Technology", "SHOP": "Technology", "TSM": "Technology",
    "ASML": "Technology", "QCOM": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "MU": "Technology", "MRVL": "Technology", "STX": "Technology", "WDC": "Technology",
    "MCHP": "Technology", "ADI": "Technology", "AVGO": "Technology", "NXPI": "Technology",
    
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials", "GS": "Financials",
    "MS": "Financials", "BLK": "Financials", "SCHW": "Financials", "IBKR": "Financials",
    "CME": "Financials", "ICE": "Financials", "CBOE": "Financials", "V": "Financials",
    "MA": "Financials", "AXP": "Financials", "COF": "Financials", "PNC": "Financials",
    "USB": "Financials", "TD": "Financials", "BMO": "Financials", "RY": "Financials",
    
    # Healthcare
    "LLY": "Healthcare", "JNJ": "Healthcare", "UNH": "Healthcare", "MRK": "Healthcare",
    "PFE": "Healthcare", "ABBV": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "DHR": "Healthcare", "MDT": "Healthcare", "GILD": "Healthcare", "BIIB": "Healthcare",
    "VRTX": "Healthcare", "SYK": "Healthcare", "BMY": "Healthcare", "AMGN": "Healthcare",
    "REGN": "Healthcare", "ILMN": "Healthcare", "MRNA": "Healthcare", "BNTX": "Healthcare",
    
    # Industrials
    "BA": "Industrials", "CAT": "Industrials", "GE": "Industrials", "HON": "Industrials",
    "RTX": "Industrials", "LMT": "Industrials", "NOC": "Industrials", "GD": "Industrials",
    "ETN": "Industrials", "EMR": "Industrials", "ITW": "Industrials", "PCAR": "Industrials",
    "ROK": "Industrials", "TDG": "Industrials", "DOV": "Industrials", "XYL": "Industrials",
    
    # Consumer Discretionary
    "MCD": "Consumer Discretionary", "SBUX": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "YUM": "Consumer Discretionary", "CMG": "Consumer Discretionary", "DIS": "Consumer Discretionary",
    "TJX": "Consumer Discretionary", "HD": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "ROST": "Consumer Discretionary", "RCL": "Consumer Discretionary", "LVS": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary", "EXPE": "Consumer Discretionary", "MAR": "Consumer Discretionary",
    "HLT": "Consumer Discretionary", "DHI": "Consumer Discretionary", "LEN": "Consumer Discretionary",
    
    # Consumer Staples
    "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "MO": "Consumer Staples", "PM": "Consumer Staples",
    "COST": "Consumer Staples", "CL": "Consumer Staples", "KMB": "Consumer Staples",
    "GIS": "Consumer Staples", "KR": "Consumer Staples", "SYY": "Consumer Staples",
    "KDP": "Consumer Staples", "HSY": "Consumer Staples", "MDLZ": "Consumer Staples",
    
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    "OXY": "Energy", "MPC": "Energy", "VLO": "Energy", "PSX": "Energy",
    "EOG": "Energy", "MRO": "Energy", "DVN": "Energy", "OKE": "Energy",
    "EPD": "Energy", "KMI": "Energy", "LNG": "Energy", "EQNR": "Energy",
    "BP": "Energy", "SHEL": "Energy", "TTE": "Energy", "PBR": "Energy",
    
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities", "EXC": "Utilities",
    "AEP": "Utilities", "XEL": "Utilities", "WEC": "Utilities", "EQT": "Utilities",
    "SRE": "Utilities", "PPL": "Utilities", "LNT": "Utilities", "PEG": "Utilities",
    
    # Real Estate
    "PLD": "Real Estate", "AMT": "Real Estate", "CCI": "Real Estate", "PSA": "Real Estate",
    "EQIX": "Real Estate", "O": "Real Estate", "SPG": "Real Estate", "VTR": "Real Estate",
    
    # Materials
    "LIN": "Materials", "ALB": "Materials", "FCX": "Materials", "NEM": "Materials",
    "SCCO": "Materials", "RIO": "Materials", "BHP": "Materials", "VALE": "Materials",
    "MT": "Materials", "NUE": "Materials", "SQM": "Materials",
}

SECTOR_EMOJIS = {
    "Technology": "💻",
    "Healthcare": "🏥",
    "Financials": "💰",
    "Industrials": "🏭",
    "Energy": "⚡",
    "Consumer Discretionary": "🛍️",
    "Consumer Staples": "🛒",
    "Real Estate": "🏢",
    "Materials": "🪨",
    "Utilities": "⚙️",
    "Other": "📊",
}


class SectorBreakdown:
    """Analyzes sector breakdown of scan results"""
    
    @staticmethod
    def _get_sector(ticker: str) -> str:
        """Get sector for a ticker"""
        return STOCK_SECTOR_MAP.get(ticker.upper(), "Other")
    
    @staticmethod
    def analyze_results(results: List[Dict]) -> Dict:
        """
        Analyze scan results by sector
        
        Args:
            results: List of scan results from Scanner.scan()
        
        Returns:
            Dict with sector breakdown stats sorted by stock count
        """
        sector_data = {}
        
        for result in results:
            sector = result.get("sector", "Other")
            
            if sector not in sector_data:
                sector_data[sector] = {
                    "stocks": [],
                    "returns": [],
                    "count": 0,
                }
            
            sector_data[sector]["stocks"].append(result["ticker"])
            sector_data[sector]["returns"].append(result["total_return"])
            sector_data[sector]["count"] += 1
        
        # Calculate sector stats
        sector_stats = {}
        for sector, data in sector_data.items():
            avg_return = np.mean(data["returns"])
            max_return = np.max(data["returns"])
            min_return = np.min(data["returns"])
            
            sector_stats[sector] = {
                "count": data["count"],
                "stocks": data["stocks"],
                "avg_return": round(avg_return, 2),
                "max_return": round(max_return, 2),
                "min_return": round(min_return, 2),
            }
        
        # Sort by count (most stocks first)
        sorted_stats = dict(sorted(sector_stats.items(), 
                                  key=lambda x: x[1]["count"], 
                                  reverse=True))
        
        return sorted_stats
    
    @staticmethod
    def format_sector_breakdown(results: List[Dict], period: str = "1mo") -> str:
        """
        Format sector breakdown as readable report
        
        Args:
            results: List of scan results
            period: Time period (1mo, 3mo, 6mo)
        
        Returns:
            Formatted string for Telegram
        """
        if not results:
            return f"📊 No results to analyze"
        
        sector_stats = SectorBreakdown.analyze_results(results)
        
        report = f"\n{'='*70}\n"
        report += f"📈 SECTOR BREAKDOWN — {period.upper()}\n"
        report += f"{'='*70}\n\n"
        
        for sector, stats in sector_stats.items():
            emoji = SECTOR_EMOJIS.get(sector, "📊")
            report += f"{emoji} **{sector}** ({stats['count']} stock{'s' if stats['count'] != 1 else ''})\n"
            
            # List stocks in this sector with their returns
            for ticker in stats["stocks"]:
                # Find the result for this ticker to get return
                for result in results:
                    if result["ticker"] == ticker:
                        ret = result["total_return"]
                        ret_emoji = "📈" if ret > 0 else "📉"
                        report += f"   {ret_emoji} `{ticker:<6}` +{ret}%\n"
                        break
            
            # Sector summary line
            report += f"   Avg: `{stats['avg_return']:+.2f}%` | Max: `{stats['max_return']:+.2f}%` | Min: `{stats['min_return']:+.2f}%`\n"
            report += "\n"
        
        # Overall summary
        total_stocks = sum(s["count"] for s in sector_stats.values())
        avg_all_returns = np.mean([r["total_return"] for r in results])
        
        report += f"{'='*70}\n"
        report += f"📊 TOTAL: {total_stocks} stocks\n"
        report += f"📊 AVERAGE RETURN: `{avg_all_returns:+.2f}%`\n"
        report += f"{'='*70}\n"
        
        return report
    
    @staticmethod
    def get_sector_summary(results: List[Dict]) -> str:
        """Get one-line sector summary for quick view"""
        if not results:
            return "No results"
        
        sector_stats = SectorBreakdown.analyze_results(results)
        
        summary_parts = []
        for sector, stats in sector_stats.items():
            emoji = SECTOR_EMOJIS.get(sector, "📊")
            summary_parts.append(f"{emoji}{stats['count']}")
        
        return " | ".join(summary_parts)
    
    @staticmethod
    def get_top_sector(results: List[Dict]) -> tuple:
        """Get sector with most breakouts"""
        if not results:
            return None, 0
        
        sector_stats = SectorBreakdown.analyze_results(results)
        top = max(sector_stats.items(), key=lambda x: x[1]["count"])
        return top[0], top[1]["count"]
