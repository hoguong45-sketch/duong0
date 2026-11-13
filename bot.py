<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Bank Ảo Mini App</title>
    <!-- Nhúng Telegram Web App Script -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <!-- Nhúng Font Inter (giống font mặc định của Telegram) -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <!-- Nhúng FontAwesome cho các icon -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        :root {
            /* Sử dụng biến màu của Telegram nếu có, fallback về màu tối trong ảnh */
            --bg-color: var(--tg-theme-bg-color, #15161b);
            --text-color: var(--tg-theme-text-color, #ffffff);
            --hint-color: var(--tg-theme-hint-color, #8e8e93);
            --secondary-bg: #1f2026;
            --card-bg: #1a1b22;
            --border-color: #2c2d35;
            --primary-color: #3b82f6; /* Màu xanh dương */
            --header-bg: #f3d0ff; /* Màu hồng nhạt header */
            --header-text: #000000;
            --vip-gold: #fbbf24;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            padding-bottom: 80px;
            -webkit-tap-highlight-color: transparent;
        }

        /* --- HEADER GIẢ LẬP CỦA TELEGRAM --- */
        .tg-header {
            background-color: var(--header-bg);
            color: var(--header-text);
            padding: 15px 20px;
            border-radius: 0 0 20px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: relative;
            height: 90px;
        }

        .btn-close, .btn-more {
            background-color: rgba(255, 255, 255, 0.5);
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            color: #000;
            cursor: pointer;
        }

        .header-title {
            text-align: center;
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
        }

        .header-title h1 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 2px;
        }

        .header-title p {
            font-size: 13px;
            color: rgba(0, 0, 0, 0.6);
        }

        /* --- TOP NAVIGATION --- */
        .top-nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 20px;
            background: linear-gradient(180deg, #181924 0%, var(--bg-color) 100%);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            font-size: 15px;
        }

        .brand-icon {
            background: linear-gradient(135deg, #7c3aed, #3b82f6);
            width: 30px;
            height: 30px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 14px;
        }

        .top-actions {
            display: flex;
            gap: 8px;
        }

        .btn-icon {
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }

        .btn-user {
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 0 10px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            font-weight: 500;
        }

        .user-avatar {
            background-color: var(--primary-color);
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
        }

        /* --- MAIN CONTENT --- */
        .container {
            padding: 0 15px;
        }

        .main-card {
            background-color: var(--card-bg);
            border-radius: 20px;
            padding: 20px 15px;
            border: 1px solid var(--border-color);
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .section-header h2 {
            font-size: 16px;
            font-weight: 600;
        }

        .btn-create {
            background-color: #ffffff;
            color: #000000;
            border: none;
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
            position: relative;
        }

        .badge-vip {
            position: absolute;
            top: -8px;
            right: -5px;
            background-color: var(--vip-gold);
            color: #000;
            font-size: 9px;
            font-weight: 700;
            padding: 2px 5px;
            border-radius: 4px;
        }

        /* --- TABS --- */
        .tabs {
            display: flex;
            background-color: var(--secondary-bg);
            border-radius: 12px;
            padding: 4px;
            margin-bottom: 15px;
            border: 1px solid var(--border-color);
        }

        .tab {
            flex: 1;
            text-align: center;
            padding: 10px 0;
            font-size: 13px;
            color: var(--hint-color);
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
        }

        .tab.active {
            background-color: #2a2b36;
            color: #a78bfa; /* Màu tím nhạt */
            font-weight: 500;
        }

        /* --- FILTERS --- */
        .filters {
            display: flex;
            background-color: var(--secondary-bg);
            border-radius: 12px;
            margin-bottom: 15px;
            border: 1px solid var(--border-color);
            overflow: hidden;
        }

        .filter-item {
            flex: 1;
            text-align: center;
            padding: 10px 0;
            font-size: 13px;
            color: var(--hint-color);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            border-right: 1px solid var(--border-color);
        }
        
        .filter-item:last-child {
            border-right: none;
        }

        .filter-item.active {
            color: var(--text-color);
        }

        .count {
            background-color: #ffffff;
            color: #000;
            font-size: 11px;
            font-weight: 700;
            padding: 1px 6px;
            border-radius: 10px;
        }
        
        .filter-item:not(.active) .count {
            background-color: #3f3f46;
            color: #fff;
        }

        /* --- SEARCH & SORT --- */
        .search-box {
            position: relative;
            margin-bottom: 15px;
        }

        .search-box i {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--hint-color);
        }

        .search-box input {
            width: 100%;
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 12px 12px 12px 40px;
            border-radius: 12px;
            font-size: 14px;
            outline: none;
        }
        
        .search-box input::placeholder {
            color: var(--hint-color);
        }

        .sort-row {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .sort-btn {
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 10px 15px;
            border-radius: 12px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
            justify-content: center;
        }

        .view-toggles {
            display: flex;
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 4px;
        }

        .view-toggles i {
            padding: 6px 10px;
            font-size: 14px;
            color: var(--hint-color);
        }
        
        .view-toggles i.active {
            color: var(--text-color);
        }

        /* --- EMPTY STATE --- */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            margin-bottom: 20px;
        }

        .empty-icon {
            width: 70px;
            height: 70px;
            background-color: #2a2b36;
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 30px;
            color: #3b82f6; /* Icon màu xanh */
            margin: 0 auto 20px;
            border: 1px solid #3f3f46;
        }

        .empty-state h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 10px;
            line-height: 1.4;
        }

        .empty-state p {
            font-size: 13px;
            color: var(--hint-color);
            line-height: 1.5;
            margin-bottom: 25px;
        }

        .btn-primary {
            background-color: #ffffff;
            color: #000000;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 14px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        /* --- FLOATING ACTION BUTTON --- */
        .fab {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 56px;
            height: 56px;
            background-color: var(--primary-color);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
            border: none;
            z-index: 100;
        }
    </style>
</head>
<body>

    <!-- Header giả lập -->
    <div class="tg-header">
        <button class="btn-close"><i class="fa-solid fa-xmark"></i></button>
        <div class="header-title">
            <h1>Bank Ảo</h1>
            <p>mini app</p>
        </div>
        <button class="btn-more"><i class="fa-solid fa-ellipsis"></i></button>
    </div>

    <!-- Thanh điều hướng trên -->
    <div class="top-nav">
        <div class="brand">
            <div class="brand-icon"><i class="fa-solid fa-shield-halved"></i></div>
            BankTaAnhTu
        </div>
        <div class="top-actions">
            <button class="btn-icon"><i class="fa-solid fa-bars"></i></button>
            <button class="btn-icon"><i class="fa-regular fa-sun"></i></button>
            <button class="btn-user">
                <span class="user-avatar">T</span>
                TO QUOC ...
                <i class="fa-solid fa-chevron-down" style="font-size: 10px; margin-left: 2px;"></i>
            </button>
        </div>
    </div>

    <!-- Nội dung chính -->
    <div class="container">
        <div class="main-card">
            <!-- Tiêu đề & Nút Tạo -->
            <div class="section-header">
                <h2>Quản Lý Tài Khoản Ngân Hàng</h2>
                <button class="btn-create">
                    <i class="fa-solid fa-plus"></i> Tạo Bank
                    <span class="badge-vip">VIP</span>
                </button>
            </div>

            <!-- Tabs -->
            <div class="tabs">
                <div class="tab active"><i class="fa-solid fa-crown"></i> Gói VIP</div>
                <div class="tab"><i class="fa-solid fa-gift"></i> Ơd</div>
                <div class="tab"><i class="fa-solid fa-ticket"></i> Giftcode</div>
                <div class="tab"><i class="fa-solid fa-lock"></i> Đổi MK</div>
            </div>

            <!-- Bộ lọc -->
            <div class="filters">
                <div class="filter-item active">Tất cả <span class="count">0</span></div>
                <div class="filter-item">Sắp hạn <span class="count">0</span></div>
                <div class="filter-item">VIP <span class="count">0</span></div>
                <div class="filter-item">Thường <span class="count">0</span></div>
            </div>

            <!-- Tìm kiếm -->
            <div class="search-box">
                <i class="fa-solid fa-magnifying-glass"></i>
                <input type="text" placeholder="Tìm STK, chủ tài khoản, SĐT...">
            </div>

            <!-- Sắp xếp -->
            <div class="sort-row">
                <button class="sort-btn">Sắp hết hạn trước <i class="fa-solid fa-arrow-down-up-across-line"></i></button>
                <button class="sort-btn">9 thẻ <i class="fa-solid fa-arrow-down-up-across-line"></i></button>
                <div class="view-toggles">
                    <i class="fa-solid fa-border-all active"></i>
                    <i class="fa-solid fa-list-ul"></i>
                </div>
            </div>

            <!-- Trạng thái trống (Empty State) -->
            <div class="empty-state">
                <div class="empty-icon">
                    <i class="fa-solid fa-building-columns"></i>
                </div>
                <h3>Không tìm thấy tài khoản ngân hàng nào phù hợp</h3>
                <p>Bạn chưa khởi tạo tài khoản ngân hàng ảo nào. Hãy bấm nút bên dưới để tạo tài khoản đầu tiên.</p>
                <button class="btn-primary"><i class="fa-solid fa-plus"></i> Tạo Bank Mới</button>
            </div>
        </div>
    </div>

    <!-- Nút nổi (Floating Action Button) -->
    <button class="fab">
        <i class="fa-regular fa-compass"></i>
    </button>

    <script>
        // Khởi tạo Telegram Web App
        let tg = window.Telegram.WebApp;
        
        // Mở rộng app toàn màn hình
        tg.expand();

        // Thiết lập màu nền header Telegram (nếu chạy thực tế trên app)
        tg.setHeaderColor('#f3d0ff');
        tg.setBackgroundColor('#15161b');

        // Xử lý sự kiện click cho các Tab
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
            });
        });

        // Xử lý sự kiện click cho Bộ lọc
        const filters = document.querySelectorAll('.filter-item');
        filters.forEach(filter => {
            filter.addEventListener('click', () => {
                filters.forEach(f => f.classList.remove('active'));
                filter.classList.add('active');
            });
        });
    </script>
</body>
</html>
