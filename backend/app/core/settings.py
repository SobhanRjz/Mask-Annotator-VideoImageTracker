from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    model_id: str = 'facebook/sam2.1-hiera-small'
    data_root: Path = Path('/data')
    frontend_origin: str = 'http://localhost:8092'
    default_tracking_step: int = 5
    jpeg_quality: int = 92

    @property
    def db_path(self) -> Path: return self.data_root / 'annotator.db'
    @property
    def media_root(self) -> Path: return self.data_root / 'media'
    @property
    def mask_root(self) -> Path: return self.data_root / 'masks'
    @property
    def export_root(self) -> Path: return self.data_root / 'exports'
settings = Settings()
