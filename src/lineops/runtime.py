"""Ensamblado del asistente: base de planta, cliente de visión, procedimientos, política, memoria y agente."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .agent import Agent
from .images import ImageStore
from .knowledge import KnowledgeBase
from .llm import LLMProvider, build_provider
from .memory import SessionStore
from .plant.db import connect
from .plant.seed import SIM_NOW, seed
from .policy import Executor
from .settings import AgentSettings
from .vision_client import VisionClient


@dataclass
class Runtime:
    settings: AgentSettings
    con: object
    executor: Executor
    sessions: SessionStore
    images: ImageStore
    agent: Agent
    now: datetime


def build(settings: AgentSettings | None = None, llm: LLMProvider | None = None, vision: VisionClient | None = None,
          now: datetime = SIM_NOW) -> Runtime:
    settings = settings or AgentSettings.from_env()
    con = connect(settings.plant_db)
    seed(con)
    vision = vision or VisionClient(settings.vision_url, settings.vision_api_key, settings.vision_timeout_s,
                                    settings.vision_retries)
    images = ImageStore(con, settings.uploads_dir, settings.image_ttl_hours)
    executor = Executor(con, vision, KnowledgeBase(settings.sops_dir), images, settings, now)
    sessions = SessionStore(con, settings.history_max_messages, settings.history_keep_chars)
    agent = Agent(llm or build_provider(settings), executor, sessions, settings, now)
    return Runtime(settings, con, executor, sessions, images, agent, now)
