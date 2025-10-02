# Updated Demslayer _send_buy_telegram method for compact formatting

async def _send_buy_telegram(self, ticker: str, strike: float, side: str, expiry: str,
                            stock_conid: int, option_conid: Optional[int], message: str) -> Dict[str, Any]:
    """Send BUY alert Telegram message in compact format"""
    try:
        # Format the message in original compact style
        side_short = "C" if side == "CALL" else "P"
        emoji = "🔴 📉" if side == "PUT" else "🟢 📈"
        formatted_expiry = _format_expiry_for_display(expiry)
        
        # Build message in original compact format
        telegram_message = f"🚨 {self.alerter_name.upper()}\n{message}\n\n"
        telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"
        
        # Add compact links
        links = []
        if stock_conid:
            chain_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{stock_conid}/option/option.chain?source=onebar&u=false"
            links.append(f"<a href='{chain_link}'>Option Chain</a>")
        
        if option_conid:
            quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
            links.append(f"<a href='{quote_link}'>🔗 Option Quote</a>")
        
        if links:
            telegram_message += f"  {' | '.join(links)}"
        
        # Send via simple telegram service
        result = await telegram_service.send_lite_alert(telegram_message)
        
        return result
        
    except Exception as e:
        logger.error(f"Error sending buy telegram: {e}")
        return {"success": False, "error": str(e)}