from app.services.handlers.real_day_trading_handler import RealDayTradingHandler

if __name__ == '__main__':
    h = RealDayTradingHandler()
    res = h.process_notification('Real Day Trading', 'Long $TSLA', '')
    print('RESULT:', res)
