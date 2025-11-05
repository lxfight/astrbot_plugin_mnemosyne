"""
Mnemosyne Admin Panel 服务器
提供Web界面管理功能
"""

import asyncio
import os
import secrets

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

    def __init__(self, plugin_instance, port: int = 8000, host: str = "127.0.0.1"):
        """
        初始化服务器

        Args:
            plugin_instance: Mnemosyne 插件实例
            port: 服务器端口
            host: 服务器主机
        """
        self.plugin = plugin_instance
        self.port = port
        self.host = host
        self.app = FastAPI(
            title="Mnemosyne Admin Panel",
            description="Mnemosyne 插件的 Web 管理面板",
            version="1.0.0",
        )

        # 配置日志
        self.logger = LogManager.GetLogger(log_name="AdminPanelServer")

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
        admin_panel_config = self.plugin.config.get("admin_panel", {})
        api_key = admin_panel_config.get("api_key", "").strip()
        if api_key:
            # 为 FastAPI 应用添加认证中间件
            @self.app.middleware("http")
            async def auth_middleware_handler(request: Request, call_next):
                # 如果没有设置API密钥，则跳过认证
                if not api_key:
                    return await call_next(request)

                # 公开路径：不需要认证的路径
                public_paths = [
                    "/",  # 主页
                    "/health",  # 健康检查
                    "/static",  # 静态资源
                ]
                
                # 检查是否是公开路径
                path = request.url.path
                is_public = any(path.startswith(public_path) for public_path in public_paths)
                
                # 公开路径直接放行
                if is_public:
                    return await call_next(request)

                # API 路径需要认证
                # 检查请求头中的 API Key
                request_api_key = request.headers.get(
                    "X-API-Key"
                ) or request.headers.get("x-api-key")

                # 使用常量时间比较防止时序攻击
                if not request_api_key or not secrets.compare_digest(
                    request_api_key, api_key
                ):
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=401,
                        content={"error": "Unauthorized", "message": "Invalid API Key"},
                    )

                response = await call_next(request)
                return response

    def _setup_static_files(self):
        """配置静态文件"""
        # 获取当前文件的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(current_dir, "static")

        # 挂载静态文件目录
        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def _setup_routes(self):
        """配置路由"""

        # 主页路由
        @self.app.get("/", response_class=HTMLResponse)
        async def read_root(request: Request):
            current_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = os.path.join(current_dir, "templates")
            templates = Jinja2Templates(directory=templates_dir)
            return templates.TemplateResponse("index.html", {"request": request})

        # 健康检查
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "plugin": "mnemosyne"}

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
