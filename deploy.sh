#!/bin/bash
# =====================================================================
# SmartClean 一鍵部署腳本
# =====================================================================
# 使用方式: ./deploy.sh [選項]
#
# 選項:
#   -d, --docker     使用 Docker 部署
#   -n, --native    使用本地部署
#   -r, --restart   重啟服務
#   -s, --stop      停止服務
#   -h, --help      顯示幫助
#
# 示例:
#   ./deploy.sh              # 交互式選擇
#   ./deploy.sh --docker    # Docker 部署
#   ./deploy.sh --restart   # 重啟服務
# =====================================================================

set -e

# 顏色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 變量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"
PROJECT_NAME="smartclean"

# 打印函數
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 顯示幫助
show_help() {
    echo "SmartClean 一鍵部署腳本"
    echo ""
    echo "使用方法: $0 [選項]"
    echo ""
    echo "選項:"
    echo "  -d, --docker     使用 Docker 部署"
    echo "  -n, --native    使用本地部署"
    echo "  -r, --restart   重啟服務"
    echo "  -s, --stop      停止服務"
    echo "  -h, --help      顯示幫助"
    echo ""
    echo "示例:"
    echo "  $0              # 交互式選擇"
    echo "  $0 --docker    # Docker 部署"
    echo "  $0 --restart   # 重啟服務"
}

# 檢查權限
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_warning "建議使用 root 權限運行: sudo $0"
    fi
}

# 檢查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安裝"
        exit 1
    fi
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose 未安裝"
        exit 1
    fi
    print_success "Docker 已就緒"
}

# 檢查 PostgreSQL
check_postgres() {
    if command -v psql &> /dev/null; then
        print_success "PostgreSQL 客戶端已安裝"
    else
        print_warning "PostgreSQL 客戶端未安裝"
    fi
}

# 檢查 Redis
check_redis() {
    if command -v redis-cli &> /dev/null; then
        print_success "Redis 客戶端已安裝"
    else
        print_warning "Redis 客戶端未安裝"
    fi
}

# 創建環境文件
setup_env() {
    if [ ! -f "$SCRIPT_DIR/$ENV_FILE" ]; then
        if [ -f "$SCRIPT_DIR/.env.example" ]; then
            print_info "創建環境配置文件..."
            cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/$ENV_FILE"
            print_success "環境配置文件已創建: $ENV_FILE"
            print_warning "請編輯 $ENV_FILE 配置數據庫密碼等敏感信息"
        else
            print_error ".env.example 不存在"
            exit 1
        fi
    else
        print_success "環境配置文件已存在"
    fi
}

# Docker 部署
docker_deploy() {
    print_info "開始 Docker 部署..."
    
    cd "$SCRIPT_DIR"
    
    # 停止舊容器
    print_info "停止舊容器..."
    docker-compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    
    # 構建並啟動
    print_info "構建 Docker 鏡像..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    
    print_info "啟動服務..."
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # 等待服務啟動
    print_info "等待服務啟動..."
    sleep 5
    
    # 檢查狀態
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
        print_success "Docker 部署完成!"
    else
        print_error "Docker 部署失敗"
        docker-compose -f "$COMPOSE_FILE" logs
        exit 1
    fi
}

# 本地部署
native_deploy() {
    print_info "開始本地部署..."
    
    cd "$SCRIPT_DIR"
    
    # 檢查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安裝"
        exit 1
    fi
    
    # 安裝依賴
    print_info "安裝 Python 依賴..."
    pip3 install -r requirements.txt -q
    
    # 執行數據庫遷移
    print_info "執行數據庫遷移..."
    if [ -d "migrations" ]; then
        PGPASSWORD=${POSTGRES_PASSWORD:-postgres} psql -h ${POSTGRES_HOST:-localhost} -U ${POSTGRES_USER:-postgres} -d smartclean -f migrations/spatial_indexes.sql 2>/dev/null || true
    fi
    
    # 啟動服務
    print_info "啟動服務..."
    if [ -f "run_optimized.sh" ]; then
        sudo bash ./run_optimized.sh &
    else
        print_error "run_optimized.sh 不存在"
        exit 1
    fi
    
    sleep 3
    
    # 檢查狀態
    if curl -s http://localhost/health > /dev/null 2>&1; then
        print_success "本地部署完成!"
    else
        print_warning "服務可能需要更多時間啟動"
    fi
}

# 重啟服務
restart_service() {
    print_info "重啟服務..."
    
    cd "$SCRIPT_DIR"
    
    # 嘗試 Docker
    if docker ps --format "{{.Names}}" | grep -q "$PROJECT_NAME"; then
        print_info "重啟 Docker 容器..."
        docker-compose -f "$COMPOSE_FILE" restart
        print_success "Docker 服務已重啟"
        return
    fi
    
    # 嘗試本地
    pkill -f granian 2>/dev/null || true
    sleep 2
    
    if [ -f "run_optimized.sh" ]; then
        sudo bash ./run_optimized.sh &
        sleep 3
        
        if curl -s http://localhost/health > /dev/null 2>&1; then
            print_success "服務已重啟"
        else
            print_error "服務重啟失敗"
            exit 1
        fi
    else
        print_error "無法找到服務"
        exit 1
    fi
}

# 停止服務
stop_service() {
    print_info "停止服務..."
    
    cd "$SCRIPT_DIR"
    
    # Docker
    docker-compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    
    # 本地
    pkill -f granian 2>/dev/null || true
    
    print_success "服務已停止"
}

# 主函數
main() {
    echo "=========================================="
    echo "     SmartClean 一鍵部署腳本"
    echo "=========================================="
    echo ""
    
    check_root
    
    case "${1:-}" in
        -d|--docker)
            check_docker
            setup_env
            docker_deploy
            ;;
        -n|--native)
            check_postgres
            check_redis
            setup_env
            native_deploy
            ;;
        -r|--restart)
            restart_service
            ;;
        -s|--stop)
            stop_service
            ;;
        -h|--help)
            show_help
            ;;
        "")
            # 交互式選擇
            echo "請選擇部署方式:"
            echo "  1) Docker 部署 (推薦)"
            echo "  2) 本地部署"
            echo "  3) 重啟服務"
            echo "  4) 停止服務"
            echo "  5) 退出"
            echo ""
            read -p "請輸入選項 [1-5]: " choice
            
            case "$choice" in
                1)
                    check_docker
                    setup_env
                    docker_deploy
                    ;;
                2)
                    check_postgres
                    check_redis
                    setup_env
                    native_deploy
                    ;;
                3)
                    restart_service
                    ;;
                4)
                    stop_service
                    ;;
                5)
                    echo "退出"
                    exit 0
                    ;;
                *)
                    print_error "無效選項"
                    exit 1
                    ;;
            esac
            ;;
        *)
            print_error "未知選項: $1"
            show_help
            exit 1
            ;;
    esac
    
    echo ""
    echo "=========================================="
    print_success "部署完成!"
    echo "=========================================="
}

main "$@"
