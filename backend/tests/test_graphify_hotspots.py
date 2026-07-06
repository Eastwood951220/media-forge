import json
import sys
from pathlib import Path

# Add project root to path for scripts module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.analyze_graphify_hotspots import analyze_graph, is_noise_path


def test_is_noise_path_filters_generated_and_tests() -> None:
    assert is_noise_path("shared/integrations/storage_providers/clouddrive2/proto/clouddrive_pb2_grpc.py")
    assert is_noise_path("backend/tests/test_storage_worker_pipeline.py")
    assert is_noise_path("frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx")
    assert is_noise_path("scraper/tests/test_movie_result.py")
    assert not is_noise_path("backend/app/modules/crawler/runtime/executor.py")
    assert not is_noise_path("frontend/src/pages/content/movies/MovieListPage.tsx")


def test_analyze_graph_filters_noise_and_warns_when_stale(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "built_at_commit": "oldcommit",
        "nodes": [
            {
                "id": "proto",
                "label": "CloudDriveFileSrv",
                "source_file": "shared/integrations/storage_providers/clouddrive2/proto/clouddrive_pb2_grpc.py",
            },
            {
                "id": "executor",
                "label": "executor.py",
                "source_file": "backend/app/modules/crawler/runtime/executor.py",
            },
            {
                "id": "movie",
                "label": "Movie",
                "source_file": "shared/database/models/content.py",
            },
        ],
        "links": [
            {"source": "executor", "target": "movie"},
            {"source": "executor", "target": "movie"},
            {"source": "proto", "target": "movie"},
        ],
    }))

    report = analyze_graph(graph_path, top=5, repo_root=Path.cwd())

    assert "WARNING: graph built_at_commit differs from current HEAD" in report
    assert "backend/app/modules/crawler/runtime/executor.py" in report
    assert "clouddrive_pb2_grpc.py" not in report
