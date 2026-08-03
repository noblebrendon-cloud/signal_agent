import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from signal_agent.content.wtpu_channel import run_wtpu_channel

@pytest.fixture
def mock_agent():
    agent_instance = MagicMock()
    mock_response = '''```json
{
  "core_message": "People are trading their attention for someone else's certainty.",
  "hook": "Notice how quiet it gets when you stop reacting. That's not emptiness; that's clarity.",
  "video_script": "Most people don't actually think. They just repeat what feels safe. You can see it in how they argue, how they buy, how they vote. Once you realize the machine runs on your reaction, the only winning move is to stop feeding it.",
  "youtube_title": "The Price of Certainty",
  "thumbnail_text": "Stop feeding the machine.",
  "facebook_post": "Stop reacting to everything designed to make you angry. People are trading their attention for someone else's certainty. The machine needs your reaction to survive. Starve it."
}
```'''
    agent_instance.generate.return_value = mock_response
    return agent_instance

def test_wtpu_channel_isolation_and_completeness(mock_agent, tmp_path):
    # Override WTPU_OUT_DIR for testing
    with patch.dict(
        run_wtpu_channel.__globals__,
        {"WTPU_OUT_DIR": tmp_path / "wtpu"},
    ):
        thought = "Most people don't actually think. They just repeat what feels safe."
        
        # Inject test path for constraint pack so it doesn't try to look for real file if we want to mock that
        # But we'll just run it with default since the file exists
        output = run_wtpu_channel(thought, agent=mock_agent)
        
        # 1. Identity isolation
        assert output.channel_id == "WTPU_CHANNEL"
        
        # 2. Output Completeness
        assert output.core_message == "People are trading their attention for someone else's certainty."
        assert output.hook == "Notice how quiet it gets when you stop reacting. That's not emptiness; that's clarity."
        assert "Most people don't actually think" in output.video_script
        assert output.youtube_title == "The Price of Certainty"
        assert output.thumbnail_text == "Stop feeding the machine."
        assert "Starve it." in output.facebook_post
        
        # 3. Persistence Check
        today = datetime.now().strftime("%Y-%m-%d")
        expected_dir = tmp_path / "wtpu" / today
        
        assert expected_dir.exists()
        assert (expected_dir / "core_message.txt").exists()
        assert (expected_dir / "hook.txt").exists()
        assert (expected_dir / "video_script.txt").exists()
        assert (expected_dir / "youtube_title.txt").exists()
        assert (expected_dir / "thumbnail_text.txt").exists()
        assert (expected_dir / "facebook_post.txt").exists()
        assert (expected_dir / "bundle.json").exists()
        
        # Verify JSON
        bundle_data = json.loads((expected_dir / "bundle.json").read_text())
        assert bundle_data["channel_id"] == "WTPU_CHANNEL"
        assert bundle_data["youtube_title"] == "The Price of Certainty"
