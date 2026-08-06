"""统一凭证入口:一份 .env 喂四个用途,进程环境永远优先,值永不回显。"""

from __future__ import annotations

import pytest

from invoiceloop import env


@pytest.fixture
def no_legacy(tmp_path, monkeypatch):
    """把旧 vision.env 指到一个不存在的路径,免得读到开发机上的真凭证。"""
    monkeypatch.delenv(env.DISABLE_VAR, raising=False)  # 本模块就是要测文件读取
    monkeypatch.setattr(env, "LEGACY_VISION_ENV", tmp_path / "nope.env")
    for name in ("DWS_API_KEY", "NUTRIENT_API_KEY", "ANTHROPIC_API_KEY",
                 "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


class TestLookup:
    def test_env_file_supplies_all_four_purposes(self, no_legacy, monkeypatch):
        (no_legacy / ".env").write_text(
            "DWS_API_KEY=dws-1\nNUTRIENT_API_KEY=nut-1\n"
            "ANTHROPIC_API_KEY=ant-1\nDWS_API_KEYS=a,b\n", encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        assert env.credential("dws") == "dws-1"
        assert env.credential("nutrient") == "nut-1"
        assert env.credential("anthropic") == "ant-1"
        assert env.credential("dws_pool") == "a,b"

    def test_process_env_beats_the_file(self, no_legacy, monkeypatch):
        """临时 export 的 key 不许被文件里的旧值盖掉。"""
        (no_legacy / ".env").write_text("DWS_API_KEY=stale", encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        monkeypatch.setenv("DWS_API_KEY", "fresh")
        assert env.credential("dws") == "fresh"

    def test_nutrient_falls_back_to_dws_key(self, no_legacy, monkeypatch):
        (no_legacy / ".env").write_text("DWS_API_KEY=dws-only", encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        assert env.credential("nutrient") == "dws-only"

    def test_found_by_walking_up_from_a_subdir(self, no_legacy, monkeypatch):
        (no_legacy / ".env").write_text("DWS_API_KEY=k", encoding="utf-8")
        deep = no_legacy / "ws" / "runs" / "run-0001"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        assert env.credential("dws") == "k"

    def test_missing_everything_is_none_not_an_exception(self, no_legacy,
                                                         monkeypatch):
        monkeypatch.chdir(no_legacy)
        assert env.credential("dws") is None

    def test_unknown_purpose_raises(self):
        with pytest.raises(KeyError):
            env.credential("bitcoin")

    def test_quotes_and_comments_parsed(self, no_legacy, monkeypatch):
        (no_legacy / ".env").write_text(
            '# comment\nDWS_API_KEY="quoted"\n\nbroken line\n', encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        assert env.credential("dws") == "quoted", "引号剥掉,手滑的一行跳过不抛"


class TestStatus:
    def test_status_never_echoes_the_value(self, no_legacy, monkeypatch):
        (no_legacy / ".env").write_text("DWS_API_KEY=super-secret",
                                        encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        info = env.status()
        assert "super-secret" not in repr(info), "凭证值永不进 doctor 输出"
        assert info["credentials"]["dws"] == "file"
        assert info["credentials"]["anthropic"] is None

    def test_status_reports_source_env(self, no_legacy, monkeypatch):
        monkeypatch.chdir(no_legacy)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        assert env.status()["credentials"]["anthropic"] == "env"


class TestCallSitesUseIt:
    def test_dws_client_reads_the_project_env(self, no_legacy, monkeypatch):
        """dws_client 以前只认 os.environ —— .env 里配了也跑不通。"""
        from invoiceloop import dws_client

        (no_legacy / ".env").write_text("DWS_API_KEY=from-file", encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        seen = {}

        def fake_post(url, **kw):
            seen["auth"] = kw["headers"]["Authorization"]
            raise RuntimeError("stop-here")

        monkeypatch.setattr(dws_client.requests, "post", fake_post)
        (no_legacy / "d.pdf").write_bytes(b"%PDF-1.4")
        with pytest.raises(RuntimeError, match="stop-here"):
            dws_client.extract(no_legacy / "d.pdf", {}, doc_id="d")
        assert seen["auth"] == "Bearer from-file"

    def test_vision_credentials_read_the_project_env(self, no_legacy, monkeypatch):
        from invoiceloop import vision_ingest

        (no_legacy / ".env").write_text(
            "ANTHROPIC_API_KEY=vk\nANTHROPIC_BASE_URL=https://proxy.example/\n",
            encoding="utf-8")
        monkeypatch.chdir(no_legacy)
        key, base, _model = vision_ingest._credentials()
        assert key == "vk" and base == "https://proxy.example"
