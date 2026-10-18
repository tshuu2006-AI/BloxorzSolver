"""Chạy game Bloxorz có GUI:  python play.py [classic|custom] [số màn]"""

if __name__ == "__main__":
    # Import trong khối này để tiến trình con của multiprocessing (nút "Compare all")
    # không phải nạp pygame và cả GUI khi khởi động.
    from App.GUI.app import main

    main()
