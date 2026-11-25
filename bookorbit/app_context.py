"""Builds the FileStore and all services once (SRS 4.24 MainWindow.run step 1).

Wiring follows the collaboration diagram (SRS Figure 1): StatusManager is shared
by WalletService, PurchaseService and WarningService, because it is the only
class allowed to change a role or status.
"""
import threading
from dataclasses import dataclass, field

from bookorbit.ai.biometrics import BiometricEngine, get_engine
from bookorbit.ai.covers import CoverIndex, get_cover_embedder
from bookorbit.ai.llm import LLMClient, get_llm
from bookorbit.ai.rag import RAGRetriever
from bookorbit.ai.recommendations import RecommendationEngine
from bookorbit.config import load_config
from bookorbit.persistence.filestore import FileStore
from bookorbit.services.auth import AuthService
from bookorbit.services.catalog import CatalogService
from bookorbit.services.chatbot import ChatbotService
from bookorbit.services.companion import ReadingCompanion
from bookorbit.services.moderation import ModerationEngine, TabooService
from bookorbit.services.purchases import PurchaseService
from bookorbit.services.ratings import RatingService
from bookorbit.services.reviews import ReviewService
from bookorbit.services.status import StatusManager
from bookorbit.services.wallet import WalletService
from bookorbit.services.warnings import WarningService


@dataclass
class AppContext:
    config: dict
    fs: FileStore
    bio: BiometricEngine
    llm: LLMClient                 # SRS 4.22 (mock / real / offline)
    auth: AuthService
    status: StatusManager
    wallet: WalletService
    purchases: PurchaseService
    taboo: TabooService
    moderation: ModerationEngine
    warnings: WarningService
    ratings: RatingService
    reviews: ReviewService
    catalog: CatalogService
    recs: RecommendationEngine
    rag: RAGRetriever              # SRS 4.21
    covers: CoverIndex             # SRS 4.9 (UC-04 cover search)
    chatbot: ChatbotService        # SRS 4.20 (UC-12, UC-13)
    companion: ReadingCompanion    # SRS 4.23 (UC-14)
    ai_ready: threading.Event = field(default_factory=threading.Event)   # set when indexing is done


def build_context(config: dict | None = None, data_dir: str | None = None) -> AppContext:
    cfg = config or load_config()
    fs = FileStore(data_dir or cfg["DATA_DIR"])
    bio = get_engine(fs, cfg["BIOMETRIC_MODE"], cfg["YOLO_FACE_WEIGHTS"])
    llm = get_llm(cfg)
    status = StatusManager(fs)
    wallet = WalletService(fs, status)
    purchases = PurchaseService(fs, wallet, status)
    taboo = TabooService(fs)
    moderation = ModerationEngine(taboo)
    warnings = WarningService(fs, status)
    ratings = RatingService(fs)
    reviews = ReviewService(fs, moderation, warnings, ratings, purchases)
    rag = RAGRetriever(fs, llm)
    covers = CoverIndex(fs, get_cover_embedder(cfg))
    return AppContext(
        config=cfg, fs=fs, bio=bio, llm=llm, auth=AuthService(fs, bio), status=status, wallet=wallet,
        purchases=purchases, taboo=taboo, moderation=moderation, warnings=warnings, ratings=ratings,
        reviews=reviews, catalog=CatalogService(fs, reviews, covers=covers, purchases=purchases),
        recs=RecommendationEngine(fs), rag=rag, covers=covers, chatbot=ChatbotService(fs, rag, llm),
        companion=ReadingCompanion(fs, rag, llm, purchases))


def build_ai_indexes(ctx: AppContext) -> None:
    """SRS 4.24 MainWindow.run: CoverIndex.build(); RAGRetriever.build_index().
    Always sets ctx.ai_ready, even if a model is offline, so nobody waits forever."""
    try:
        ctx.covers.build()
        ctx.rag.build_index()
    finally:
        ctx.ai_ready.set()


def start_ai_indexing(ctx: AppContext) -> threading.Thread:
    """Run build_ai_indexes in a background thread so the window opens at once
    (SRS 4.24: "background thread, splash text meanwhile"). Only this thread writes
    rag_chunks.txt; FileStore's lock keeps its book updates safe next to the GUI's."""
    t = threading.Thread(target=build_ai_indexes, args=(ctx,), name="ai-indexing", daemon=True)
    t.start()
    return t
