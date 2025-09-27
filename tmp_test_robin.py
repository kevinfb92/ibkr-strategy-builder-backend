"""Quick test script for RobinDaHoodHandler parsing logic"""
from app.services.handlers.robin_da_hood_handler import RobinDaHoodHandler


def run_tests():
    h = RobinDaHoodHandler()

    samples = [
        ("robin-da-hood", "SPY 647C @.68 9/5", ""),
        ("robin-da-hood", "ROBIN ALERT: AAPL 150.5P 10/12 @1.2", ""),
        ("robin-da-hood", "no contract here, just noise", ""),
        ("notice", "AMZN 3200C", "robin-da-hood in title"),
    ]

    for title, msg, sub in samples:
        out = h.process_notification(title, msg, sub)
        print('---')
        print('TITLE:', title)
        print('MSG:', msg)
        print('OUT:', out)


if __name__ == '__main__':
    run_tests()
