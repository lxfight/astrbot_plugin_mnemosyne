"""
Mnemosyne Admin Panel 服务器
提供Web界面管理功能
"""

import asyncio
import os
import secrets
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from astrbot.core.log import LogManager

from .routers import setup_all_routes
from .services.monitoring_service import MonitoringService


class AdminPanelServer:
    """
    Admin Panel Web 服务器
    """

    def __init__(
        self,
        plugin_instance,
        port: int = 8000,
        host: str = "127.0.0.1",
        api_key: str = "",
        data_dir: str | None = None,
    ):
        """
        初始化服务器

        Args:
            plugin_instance: Mnemosyne 插件实例
            port: 服务器端口
            host: 服务器主机
            api_key: API密钥（如果为空则从配置中读取）
            data_dir: 数据目录路径（用于存储认证token等数据）
        """
        self.plugin = plugin_instance
        self.port = port
        self.host = host
        self.api_key = api_key  # 保存传入的API密钥
        self.data_dir = data_dir  # 保存数据目录
        self.app = FastAPI(
            title="Mnemosyne Admin Panel",
            description="Mnemosyne 插件的 Web 管理面板",
            version="1.0.0",
        )

        # 配置日志
        self.logger = LogManager.GetLogger(log_name="AdminPanelServer")

        # 会话管理：存储已认证的会话令牌及其过期时间
        # 格式: {token: expiry_timestamp}
        self.authenticated_sessions: dict[str, float] = {}
        self.session_timeout = 3600  # 会话超时时间（秒），默认1小时

        # 服务器启动时间戳，用于识别重启
        self.server_start_time = time.time()

        # 配置中间件
        self._setup_middleware()

        # 挂载静态文件
        self._setup_static_files()

        # 配置路由
        self._setup_routes()

        # 监控服务
        self.monitoring_service = MonitoringService(self.plugin)

        # 服务器实例
        self.server_instance = None
        self.is_running = False

    def _setup_middleware(self):
        """配置中间件"""
        # CORS 中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # API 密钥认证中间件（只对 API 路由进行认证）
        # 优先使用传入的api_key，如果没有则从配置中读取
        api_key = (
            self.api_key
            or self.plugin.config.get("admin_panel", {}).get("api_key", "").strip()
        )
        if api_key:
            # 为 FastAPI 应用添加认证中间件
            @self.app.middleware("http")
            async def auth_middleware_handler(request: Request, call_next):
                # 如果没有设置API密钥，则跳过认证
                if not api_key:
                    return await call_next(request)

                # 公开路径：不需要认证的路径
                public_paths = [
                    "/",  # 登录页面
                    "/dashboard",  # 管理面板（由前端JS检查认证）
                    "/health",  # 健康检查
                    "/static",  # 静态资源
                    "/api/auth/login",  # 登录接口
                ]

                # 检查是否是公开路径
                path = request.url.path
                is_public = any(
                    path.startswith(public_path) for public_path in public_paths
                )

                # 公开路径直接放行
                if is_public:
                    return await call_next(request)

                # API 路径需要认证
                # 清理过期的会话
                self._cleanup_expired_sessions()

                # 首先检查会话令牌
                session_token = request.headers.get(
                    "X-Session-Token"
                ) or request.headers.get("x-session-token")

                if session_token and self._is_session_valid(session_token):
                    # 会话有效，刷新过期时间
                    self.authenticated_sessions[session_token] = (
                        time.time() + self.session_timeout
                    )
                    response = await call_next(request)
                    return response

                # 如果没有有效的会话令牌，检查 API Key（用于首次认证）
                request_api_key = request.headers.get(
                    "X-API-Key"
                ) or request.headers.get("x-api-key")

                # 使用常量时间比较防止时序攻击
                if request_api_key and secrets.compare_digest(request_api_key, api_key):
                    # API Key 验证成功，创建新会话
                    new_session_token = secrets.token_urlsafe(32)
                    self.authenticated_sessions[new_session_token] = (
                        time.time() + self.session_timeout
                    )

                    response = await call_next(request)
                    # 在响应头中返回会话令牌
                    response.headers["X-Session-Token"] = new_session_token
                    return response

                # 认证失败
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Unauthorized",
                        "message": "Invalid or expired credentials. Please authenticate with API Key.",
                        "server_start_time": self.server_start_time,  # 返回服务器启动时间，客户端可以用来检测重启
                    },
                )

                response = await call_next(request)
                return response

    def _is_session_valid(self, token: str) -> bool:
        """检查会话令牌是否有效"""
        if token not in self.authenticated_sessions:
            return False

        expiry_time = self.authenticated_sessions[token]
        if time.time() > expiry_time:
            # 会话已过期，删除
            del self.authenticated_sessions[token]
            return False

        return True

    def _cleanup_expired_sessions(self):
        """清理过期的会话"""
        current_time = time.time()
        expired_tokens = [
            token
            for token, expiry in self.authenticated_sessions.items()
            if current_time > expiry
        ]
        for token in expired_tokens:
            del self.authenticated_sessions[token]

    def _setup_static_files(self):
        """配置静态文件"""
        # 获取当前文件的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(current_dir, "static")

        # 挂载静态文件目录
        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def _setup_routes(self):
        """配置路由"""

        # 登录页面路由
        @self.app.get("/", response_class=HTMLResponse)
        async def read_root(request: Request):
            current_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = os.path.join(current_dir, "templates")
            templates = Jinja2Templates(directory=templates_dir)
            return templates.TemplateResponse("login.html", {"request": request})

        # 管理面板主页（直接显示，由前端 JS 检查认证）
        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard(request: Request):
            # 直接返回管理面板页面，让前端 JavaScript 检查会话
            current_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = os.path.join(current_dir, "templates")
            templates = Jinja2Templates(directory=templates_dir)
            return templates.TemplateResponse("index.html", {"request": request})

        # 健康检查
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "plugin": "mnemosyne",
                "server_start_time": self.server_start_time,
            }

        # 登录接口（用于验证API密钥并获取会话令牌）
        @self.app.post("/api/auth/login")
        async def login(request: Request):
            try:
                data = await request.json()
                provided_api_key = data.get("api_key", "").strip()

                # 获取当前有效的 API 密钥
                api_key = (
                    self.api_key
                    or self.plugin.config.get("admin_panel", {})
                    .get("api_key", "")
                    .strip()
                )

                if not api_key:
                    raise HTTPException(
                        status_code=500, detail="Server API key not configured"
                    )

                # 验证 API 密钥
                if not provided_api_key or not secrets.compare_digest(
                    provided_api_key, api_key
                ):
                    return JSONResponse(
                        status_code=401,
                        content={"error": "Unauthorized", "message": "Invalid API Key"},
                    )

                # 生成会话令牌
                session_token = secrets.token_urlsafe(32)
                self.authenticated_sessions[session_token] = (
                    time.time() + self.session_timeout
                )

                self.logger.info(f"新会话已创建，过期时间: {self.session_timeout}秒")

                return JSONResponse(
                    content={
                        "success": True,
                        "session_token": session_token,
                        "expires_in": self.session_timeout,
                        "server_start_time": self.server_start_time,
                    }
                )
            except Exception as e:
                self.logger.error(f"登录失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 登出接口（撤销会话令牌）
        @self.app.post("/api/auth/logout")
        async def logout(request: Request):
            session_token = request.headers.get(
                "X-Session-Token"
            ) or request.headers.get("x-session-token")

            if session_token and session_token in self.authenticated_sessions:
                del self.authenticated_sessions[session_token]
                self.logger.info("会话已注销")
                return JSONResponse(
                    content={"success": True, "message": "Logged out successfully"}
                )

            return JSONResponse(
                content={"success": False, "message": "No active session found"}
            )

        # 获取系统状态
        @self.app.get("/api/system/status")
        async def get_system_status():
            try:
                status = await self.monitoring_service.get_system_status()
                return JSONResponse(content=status.to_dict())
            except Exception as e:
                self.logger.error(f"获取系统状态失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 获取性能指标
        @self.app.get("/api/system/performance")
        async def get_performance_metrics():
            try:
                metrics = self.monitoring_service.get_performance_metrics()
                return JSONResponse(content=metrics.to_dict())
            except Exception as e:
                self.logger.error(f"获取性能指标失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 获取资源使用情况
        @self.app.get("/api/system/resources")
        async def get_resource_usage():
            try:
                usage = await self.monitoring_service.get_resource_usage()
                return JSONResponse(content=usage.to_dict())
            except Exception as e:
                self.logger.error(f"获取资源使用情况失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 配置相关API
        @self.app.get("/api/config")
        async def get_config():
            try:
                # 返回插件配置（移除敏感信息）
                config = self.plugin.config.copy()
                if "authentication" in config:
                    auth_config = config["authentication"].copy()
                    if "password" in auth_config:
                        auth_config["password"] = "***"
                    config["authentication"] = auth_config
                return JSONResponse(content=config)
            except Exception as e:
                self.logger.error(f"获取配置失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/config")
        async def update_config(request: Request):
            try:
                data = await request.json()
                # 更新配置
                for key, value in data.items():
                    self.plugin.config[key] = value
                # 保存配置
                self.plugin.save_config()
                return JSONResponse(content={"success": True})
            except Exception as e:
                self.logger.error(f"更新配置失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 设置所有路由
        setup_all_routes(self.app, self.plugin)

    async def start(self):
        """启动服务器"""
        if self.is_running:
            self.logger.warning("服务器已在运行中")
            return

        self.logger.info(f"正在启动 Admin Panel 服务器在 {self.host}:{self.port}")

        # 创建配置
        config = uvicorn.Config(
            self.app, host=self.host, port=self.port, log_level="info"
        )
        self.server_instance = uvicorn.Server(config)

        # 启动服务器
        self.is_running = True
        try:
            await self.server_instance.serve()
        except Exception as e:
            self.logger.error(f"服务器启动失败: {e}")
            raise
        finally:
            self.is_running = False

    async def stop(self):
        """停止服务器"""
        if self.server_instance:
            self.logger.info("正在停止 Admin Panel 服务器")
            self.server_instance.should_exit = True
            self.is_running = False

    def run_in_thread(self):
        """在独立线程中运行服务器"""

        def run():
            asyncio.run(self.start())

        import threading

        server_thread = threading.Thread(target=run, daemon=True)
        server_thread.start()
        return server_thread
