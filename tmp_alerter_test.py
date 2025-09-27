from app.services.handlers.demslayer_spx_alerts_handler import DemslayerSpxAlertsHandler
from app.services.handlers.robin_da_hood_handler import RobinDaHoodHandler

handler = RobinDaHoodHandler()

# Test 1: normal message
msg1 = 'RobinDaHood 6500P'
res1 = handler._extract_contract_info('', msg1)
print('TEST 1 - input:', msg1)
print('TEST 1 - result:', res1)

# Test 2: fragmented message with newlines
msg2 = 'Robin\n\nDaHood 6500P'
res2 = handler._extract_contract_info('', msg2)
print('\nTEST 2 - input:', repr(msg2))
print('TEST 2 - result:', res2)

# Test 3: message without contract
msg3 = 'RobinDaHood no contract here'
res3 = handler._extract_contract_info('', msg3)
print('\nTEST 3 - input:', msg3)
print('TEST 3 - result:', res3)
