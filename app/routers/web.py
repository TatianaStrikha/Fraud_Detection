# =============================================
# Web-интерфейс
# =============================================
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

# Создаем изолированный роутер для веб-интерфейса
web_router = APIRouter(tags=["Web Interface"])

# Находим точный путь к папке, где лежит сам проект, и строим прямую дорогу к templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@web_router.get("/", response_class=HTMLResponse)
async def render_homepage(request: Request):
    """
    Отображает главную страницу демо-сайта антифрода.
    Сюда пользователь будет заходить через браузер по адресу http://localhost:8080/
    """
    # Передаем обязательный параметр request, который требует Jinja2
    return templates.TemplateResponse(request, "index.html")

