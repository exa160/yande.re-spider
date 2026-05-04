"""
配置业务逻辑层
"""

from src.common import config
from src.common.constant import path_constant
from src.common.settings import ApiConfig, DownloaderConfig, DatabaseConfig


class ConfigService:
    """配置服务类"""

    @staticmethod
    def get_system_config():
        """获取系统配置"""
        return config

    @staticmethod
    def update_api_config(api_config: ApiConfig) -> bool:
        """
        更新 API 配置

        Args:
            api_config: API 配置数据

        Returns:
            是否成功
        """
        try:
            tmp_config = config.yande_api.model_dump(mode="json")
            tmp_config.update(api_config)
            config.update_config(ApiConfig.model_validate(tmp_config))
            return True
        except Exception:
            return False

    @staticmethod
    def update_downloader_config(down_config: DownloaderConfig) -> bool:
        """
        更新下载器配置

        Args:
            down_config: 下载器配置数据

        Returns:
            是否成功
        """
        try:
            config.update_config(DownloaderConfig.model_validate(down_config))
            return True
        except Exception:
            return False

    @staticmethod
    def update_database_config(database_config: DatabaseConfig) -> bool:
        """
        更新数据库配置

        Args:
            database_config: 数据库配置数据

        Returns:
            是否成功
        """
        try:
            config.update_config(DatabaseConfig.model_validate(database_config))
            return True
        except Exception:
            return False

    @staticmethod
    def test_database_connection(database_config: DatabaseConfig) -> dict:
        """
        测试数据库连接

        Args:
            database_config: 数据库配置

        Returns:
            {"success": bool, "message": str}
        """
        try:
            if database_config.enable:
                return ConfigService._test_mariadb_connection(database_config)
            else:
                return ConfigService._test_sqlite_connection()
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    @staticmethod
    def _test_mariadb_connection(database_config: DatabaseConfig) -> dict:
        """测试 MariaDB 连接"""
        from sqlalchemy import create_engine

        engine = create_engine(
            f"mariadb+mariadbconnector://{database_config.user}:{database_config.password}@"
            f"{database_config.host}:{database_config.port}/{database_config.schema_name}?charset=utf8"
        )
        conn = engine.connect()
        conn.close()
        return {"success": True, "message": "数据库连接成功"}

    @staticmethod
    def _test_sqlite_connection() -> dict:
        """测试 SQLite 连接"""
        db_path = path_constant.sqlite_file
        if db_path.exists():
            return {"success": True, "message": "SQLite数据库文件存在"}
        return {"success": True, "message": "SQLite数据库未配置，使用默认路径"}

    @staticmethod
    def reset_config(section: str) -> tuple[bool, str]:
        """
        重置配置

        Args:
            section: 配置段 (api/downloader/database)

        Returns:
            (成功与否, 消息)
        """

        reset_map = {
            "api": ApiConfig,
            "downloader": DownloaderConfig,
            "database": DatabaseConfig,
        }

        reset_model = reset_map.get(section)
        if reset_model is None:
            return False, f"{section} not in {list(reset_map.keys())}."

        config.update_config(reset_model())
        return True, "Reset success."
