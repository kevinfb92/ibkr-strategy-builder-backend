from app.services.alerter_config import AlerterConfig

tests = [
    ("RobinDaHood", "Buy 100"),
    ("robindahood-alerts: BUY 100", ""),
    ("Some title", "this is from RobinDaHood signal"),
    ("Some title", "prefix robindahood-alerts 123C")
]

for t in tests:
    al = AlerterConfig.detect_alerter(t[0], t[1])
    print(t, "->", al)
