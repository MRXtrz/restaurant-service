

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="cafe"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker не установлен. Установите Docker сначала."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose не установлен. Установите Docker Compose сначала."
        exit 1
    fi
}

start_services() {
    print_status "Запуск всех сервисов..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d --build
    print_status "Сервисы запущены!"
    print_status "API Gateway доступен на http://localhost:8100"
    print_status "Проверка здоровья: curl http://localhost:8100/health"
}

stop_services() {
    print_status "Остановка всех сервисов..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down
    print_status "Сервисы остановлены!"
}

restart_services() {
    print_status "Перезапуск всех сервисов..."
    stop_services
    sleep 2
    start_services
}

show_status() {
    print_status "Статус сервисов:"
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps
}

show_logs() {
    if [ -z "$2" ]; then
        print_status "Логи всех сервисов (Ctrl+C для выхода):"
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f
    else
        print_status "Логи сервиса $2:"
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f "$2"
    fi
}

check_health() {
    print_status "Проверка здоровья сервисов..."
    
    services=("api-gateway:8100" "auth-service:8101" "order-service:8102" "table-service:8103" "notification-service:8104" "menu-service:8105")
    
    for service in "${services[@]}"; do
        IFS=':' read -r name port <<< "$service"
        if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
            print_status "$name: ✓ Работает"
        else
            print_warning "$name: ✗ Не отвечает"
        fi
    done
}

# Основная логика
check_docker

case "${1:-start}" in
    start)
        start_services
        sleep 3
        check_health
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        sleep 3
        check_health
        ;;
    status)
        show_status
        check_health
        ;;
    logs)
        show_logs "$@"
        ;;
    health)
        check_health
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|health}"
        echo ""
        echo "Команды:"
        echo "  start   - Запустить все сервисы"
        echo "  stop    - Остановить все сервисы"
        echo "  restart - Перезапустить все сервисы"
        echo "  status  - Показать статус сервисов"
        echo "  logs    - Показать логи (можно указать имя сервиса)"
        echo "  health  - Проверить здоровье сервисов"
        echo ""
        echo "Примеры:"
        echo "  $0 start"
        echo "  $0 logs api-gateway"
        echo "  $0 restart"
        exit 1
        ;;
esac

