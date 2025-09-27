"""
Alerter configuration and management
"""
from typing import Dict, List, Optional
import re
from enum import Enum

class AlerterType(Enum):
    """Enumeration of supported alerter types"""
    REAL_DAY_TRADING = "Real Day Trading"
    NYRLETH = "Nyrleth"
    DEMSLAYER_SPX_ALERTS = "demslayer-spx-alerts"
    PROF_AND_KIAN_ALERTS = "prof-and-kian-alerts"

# Global list of supported alerters for easy editing
SUPPORTED_ALERTERS = [
    AlerterType.REAL_DAY_TRADING.value,
    AlerterType.NYRLETH.value,
    AlerterType.DEMSLAYER_SPX_ALERTS.value,
    AlerterType.PROF_AND_KIAN_ALERTS.value
]

# Aliases map (compacted lower -> canonical supported alerter)
# Add Robindahood aliases so messages/titles containing 'robindahood-alerts' or 'RobinDaHood'
# will be recognized and normalized to the canonical 'robindahood-alerts'.
ALIAS_TO_CANONICAL: dict = {
    'robindahoodalerts': 'robindahood-alerts',
    'robindahood': 'robindahood-alerts',
    'robindahoodalert': 'robindahood-alerts',
    # Aliases for DeMsLayer renames / variants (compact form)
    'demspxslayer': 'demslayer-spx-alerts',
    'demspxslayerandleaps': 'demslayer-spx-alerts',
    'demspxslayerandleaps': 'demslayer-spx-alerts',
}

# Ensure canonical Robindahood alerter is in supported list
if 'robindahood-alerts' not in SUPPORTED_ALERTERS:
    SUPPORTED_ALERTERS.append('robindahood-alerts')

class AlerterConfig:
    """Configuration for alerter management"""
    
    @staticmethod
    def get_supported_alerters() -> List[str]:
        """Get list of supported alerter names"""
        return SUPPORTED_ALERTERS.copy()
    
    @staticmethod
    def is_supported_alerter(alerter_name: str) -> bool:
        """Check if an alerter name is supported"""
        if not alerter_name:
            return False
        return alerter_name.strip() in SUPPORTED_ALERTERS
    
    @staticmethod
    def normalize_alerter_name(alerter_name: str) -> Optional[str]:
        """Normalize alerter name to match our supported list"""
        if not alerter_name:
            return None
            
        normalized = alerter_name.strip()
        
        # Check for exact match first
        if normalized in SUPPORTED_ALERTERS:
            return normalized
            
        # Check for case-insensitive match
        for supported in SUPPORTED_ALERTERS:
            if normalized.lower() == supported.lower():
                return supported
        
        # Check if any supported alerter is contained within the input string
        for supported in SUPPORTED_ALERTERS:
            if supported.lower() in normalized.lower():
                return supported
                
        # Check alias mapping using a compacted key
        try:
            compact = re.sub(r'[^0-9a-zA-Z]+', '', normalized).lower()
            if compact in ALIAS_TO_CANONICAL:
                return ALIAS_TO_CANONICAL[compact]
        except Exception:
            pass

        return None
    
    @staticmethod
    def extract_alerter_from_message(message: str) -> tuple[Optional[str], str]:
        """
        Extract alerter name from message format: "something Nyrleth: 'rest of message'"
        Returns (alerter_name, cleaned_message)
        """
        if not message:
            return None, message
        # Normalize working copy
        msg = message.strip()

        # Check each supported alerter using several patterns so we handle
        # variants like "alerter: rest", "alerter rest", or messages that
        # start with the alerter name followed by whitespace/punctuation.
        for alerter in SUPPORTED_ALERTERS:
            # Pattern 1: explicit 'AlerterName:' marker (existing behavior)
            if f"{alerter}:" in msg:
                parts = re.split(re.escape(f"{alerter}:"), msg, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    cleaned_message = parts[1].strip()
                    # Remove surrounding quotes if present
                    if (cleaned_message.startswith("'") and cleaned_message.endswith("'")) or (cleaned_message.startswith('"') and cleaned_message.endswith('"')):
                        cleaned_message = cleaned_message[1:-1]
                    return alerter, cleaned_message

            # Pattern 2: message starts with the alerter name followed by whitespace or punctuation
            low_msg = msg.lower()
            low_alerter = alerter.lower()
            if low_msg.startswith(low_alerter):
                remainder = msg[len(alerter):].lstrip(" \t-–—:\'\"")
                cleaned_message = remainder
                # Strip surrounding quotes
                if (cleaned_message.startswith("'") and cleaned_message.endswith("'")) or (cleaned_message.startswith('"') and cleaned_message.endswith('"')):
                    cleaned_message = cleaned_message[1:-1]
                return alerter, cleaned_message

            # Pattern 3: alerter appears as a standalone token inside the message
            # e.g. "prefix demslayer-spx-alerts 6500P" -> we want the trailing part
            idx = low_msg.find(low_alerter)
            if idx != -1:
                # Ensure that the matched substring is a token boundary (preceded/followed by space or punctuation)
                before_ok = (idx == 0) or (not low_msg[idx-1].isalnum())
                after_idx = idx + len(low_alerter)
                after_ok = (after_idx >= len(low_msg)) or (not low_msg[after_idx].isalnum())
                if before_ok and after_ok:
                    remainder = msg[after_idx:].lstrip(" \t-–—:\'\"")
                    cleaned_message = remainder
                    if (cleaned_message.startswith("'") and cleaned_message.endswith("'")) or (cleaned_message.startswith('"') and cleaned_message.endswith('"')):
                        cleaned_message = cleaned_message[1:-1]
                    return alerter, cleaned_message

            # Final fallback: sometimes messages contain embedded newlines or
            # noise that break the literal token matching above (e.g.
            # "demslayer-s\n\n\nspx-alerts 6500P"). In that case, compact the
            # input by removing non-alphanumeric characters and try a normalized
            # substring match. If found, return the supported alerter and the
            # original message (handlers will still extract the contract info).
            try:
                compact_msg = re.sub(r'[^0-9a-zA-Z]+', '', msg).lower()
                # First check canonical supported names
                for supported in SUPPORTED_ALERTERS:
                    compact_supported = re.sub(r'[^0-9a-zA-Z]+', '', supported).lower()
                    if compact_supported and compact_supported in compact_msg:
                        return supported, msg
                # Then check alias mapping
                for alias_compact, canonical in ALIAS_TO_CANONICAL.items():
                    if alias_compact in compact_msg:
                        return canonical, msg
            except Exception:
                pass

            return None, message
    
    @staticmethod
    def detect_alerter(title: str, message: str, subtext: str = None) -> Optional[str]:
        """
        Detect which alerter this notification is from
        Check title first, then message pattern, then subtext
        """
        # Check title first
        if title:
            normalized = AlerterConfig.normalize_alerter_name(title)
            if normalized:
                return normalized
        
        # Check message for alerter pattern
        if message:
            alerter, _ = AlerterConfig.extract_alerter_from_message(message)
            if alerter:
                return alerter
        
        # Check subtext for alerter pattern
        if subtext:
            alerter, _ = AlerterConfig.extract_alerter_from_message(subtext)
            if alerter:
                return alerter
        
        return None
