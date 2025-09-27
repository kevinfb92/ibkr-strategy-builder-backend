"""
Contract storage service for persisting alerter contracts across server restarts
"""
import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)

class ContractStorage:
    """Service for storing and retrieving alerter contracts"""
    
    def __init__(self, storage_file: str = "alerter_contracts.json"):
        self.storage_file = storage_file
        self.storage_path = os.path.join(os.getcwd(), "data", storage_file)
        self._ensure_storage_directory()
        self.contracts = self._load_contracts()
    
    def _ensure_storage_directory(self):
        """Ensure the data directory exists"""
        data_dir = os.path.dirname(self.storage_path)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logger.info(f"Created data directory: {data_dir}")
    
    def _load_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Load contracts from storage file"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} stored contracts from {self.storage_path}")
                    return data
            else:
                logger.info(f"No existing contracts file found at {self.storage_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading contracts: {e}")
            return {}
    
    def _save_contracts(self):
        """Save contracts to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.contracts, f, indent=2, default=str)
            logger.info(f"Saved {len(self.contracts)} contracts to {self.storage_path}")
        except Exception as e:
            logger.error(f"Error saving contracts: {e}")
    
    def store_contract(self, alerter_name: str, contract_info: Dict[str, Any]):
        """
        Store a contract for a specific alerter
        
        Args:
            alerter_name: Name of the alerter (e.g., "demslayer-spx-alerts")
            contract_info: Contract information to store
        """
        try:
            # Add metadata
            contract_with_metadata = {
                **contract_info,
                "stored_at": datetime.now().isoformat(),
                "alerter": alerter_name
            }
            
            self.contracts[alerter_name] = contract_with_metadata
            self._save_contracts()
            
            logger.info(f"Stored contract for {alerter_name}: {contract_info}")
            print(f"DEBUG: Stored contract for {alerter_name}: {contract_info}")
            
        except Exception as e:
            logger.error(f"Error storing contract for {alerter_name}: {e}")
    
    def get_contract(self, alerter_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the stored contract for a specific alerter
        
        Args:
            alerter_name: Name of the alerter
            
        Returns:
            Contract info or None if not found
        """
        try:
            # Direct hit
            contract = self.contracts.get(alerter_name)
            if contract:
                logger.info(f"Retrieved stored contract for {alerter_name}: {contract}")
                print(f"DEBUG: Retrieved stored contract for {alerter_name}: {contract}")
                return contract

            # Try normalized variants to tolerate alerter naming differences
            norm = str(alerter_name or '').strip()
            # 1) lowercase key
            try_keys = [norm, norm.lower()]

            # 2) strip common suffixes like '-alerts', '_alerts', 'alerts'
            import re
            base = re.sub(r"[-_. ]?(alerts|alert|handler)$", "", norm, flags=re.IGNORECASE)
            if base and base not in try_keys:
                try_keys.append(base)

            # 3) also try title/camelcase form (e.g., robindahood -> RobinDaHood)
            try:
                camel = ''.join(p.capitalize() for p in re.split(r'[^A-Za-z0-9]+', base) if p)
                if camel and camel not in try_keys:
                    try_keys.append(camel)
            except Exception:
                pass

            for k in try_keys:
                if k in self.contracts:
                    contract = self.contracts.get(k)
                    logger.info(f"Retrieved stored contract for alias {alerter_name} -> {k}: {contract}")
                    print(f"DEBUG: Retrieved stored contract for alias {alerter_name} -> {k}: {contract}")
                    return contract

            # As a final fallback, compare normalized alphanumeric lowercase forms
            # so that variants like 'robindahood-alerts' match stored keys like 'RobinDaHood'
            try:
                def _normalize_alnum(s: str) -> str:
                    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).lower()

                # Prefer using the base (with common suffixes stripped) so that
                # 'robindahood-alerts' -> 'robindahood' will match stored 'RobinDaHood'
                target_norm = _normalize_alnum(base if base else norm)
                for stored_key in self.contracts.keys():
                    if _normalize_alnum(stored_key) == target_norm:
                        contract = self.contracts.get(stored_key)
                        logger.info(f"Retrieved stored contract for normalized alias {alerter_name} -> {stored_key}: {contract}")
                        print(f"DEBUG: Retrieved stored contract for normalized alias {alerter_name} -> {stored_key}: {contract}")
                        return contract
            except Exception:
                pass

            logger.info(f"No stored contract found for {alerter_name} (tried aliases: {try_keys})")
            print(f"DEBUG: No stored contract found for {alerter_name} (tried aliases: {try_keys})")
            return None
        except Exception as e:
            logger.error(f"Error retrieving contract for {alerter_name}: {e}")
            return None
    
    def get_all_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored contracts"""
        return self.contracts.copy()
    
    def remove_contract(self, alerter_name: str) -> bool:
        """
        Remove a stored contract for a specific alerter
        
        Args:
            alerter_name: Name of the alerter
            
        Returns:
            True if removed, False if not found
        """
        try:
            if alerter_name in self.contracts:
                del self.contracts[alerter_name]
                self._save_contracts()
                logger.info(f"Removed stored contract for {alerter_name}")
                return True
            else:
                logger.info(f"No contract to remove for {alerter_name}")
                return False
        except Exception as e:
            logger.error(f"Error removing contract for {alerter_name}: {e}")
            return False

    def migrate_contract_key(self, old_key: str, new_key: str) -> bool:
        """
        Move a stored contract from old_key to new_key. Returns True on success.
        If new_key already exists, this is a no-op and returns False.
        """
        try:
            if not old_key or not new_key:
                return False
            if old_key not in self.contracts:
                return False
            if new_key in self.contracts:
                # Don't overwrite existing new_key
                logger.info(f"Not migrating contract: target key {new_key} already exists")
                return False
            # Move and update metadata
            self.contracts[new_key] = self.contracts.pop(old_key)
            try:
                # Update the stored alerter metadata
                self.contracts[new_key]['alerter'] = new_key
                self.contracts[new_key]['migrated_from'] = old_key
                self.contracts[new_key]['migrated_at'] = datetime.now().isoformat()
            except Exception:
                pass
            self._save_contracts()
            logger.info(f"Migrated contract from {old_key} to {new_key}")
            return True
        except Exception as e:
            logger.error(f"Error migrating contract from {old_key} to {new_key}: {e}")
            return False
    
    def is_contract_expired(self, alerter_name: str) -> bool:
        """
        Check if a stored contract is expired (for 0DTE options)
        
        Args:
            alerter_name: Name of the alerter
            
        Returns:
            True if expired, False if still valid
        """
        try:
            contract = self.get_contract(alerter_name)
            if not contract:
                return True
            
            # For 0DTE options, check if it's still the same day
            expiry = contract.get('expiry')
            if expiry:
                # If expiry is in YYYYMMDD format
                if len(str(expiry)) == 8:
                    contract_date = datetime.strptime(str(expiry), '%Y%m%d').date()
                    today = date.today()
                    
                    is_expired = contract_date < today
                    if is_expired:
                        logger.info(f"Contract for {alerter_name} expired: {contract_date} < {today}")
                    
                    return is_expired
            
            # If no expiry or can't parse, consider valid
            return False
            
        except Exception as e:
            logger.error(f"Error checking expiry for {alerter_name}: {e}")
            return False
    
    def cleanup_expired_contracts(self):
        """Remove all expired contracts"""
        try:
            expired_alerters = []
            for alerter_name in list(self.contracts.keys()):
                if self.is_contract_expired(alerter_name):
                    expired_alerters.append(alerter_name)
            
            for alerter_name in expired_alerters:
                self.remove_contract(alerter_name)
                
            if expired_alerters:
                logger.info(f"Cleaned up {len(expired_alerters)} expired contracts: {expired_alerters}")
            
        except Exception as e:
            logger.error(f"Error cleaning up expired contracts: {e}")
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        return {
            "total_contracts": len(self.contracts),
            "storage_file": self.storage_path,
            "file_exists": os.path.exists(self.storage_path),
            "alerters": list(self.contracts.keys())
        }

# Global instance
contract_storage = ContractStorage()
