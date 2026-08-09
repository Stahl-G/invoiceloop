"""run 指纹:code_revision 必须说得出实话。

冻结的是**证据**,但判定证据的是代码 —— 门禁、规范化规则、路由都是代码。
所以「这批数字由哪份代码产生」和「用了哪些工件」同等重要,而前者只有
一行 git 信息在承担。
"""

from __future__ import annotations


class TestCodeRevisionCannotLookCleanerThanItIs:
    """指纹存在的意义是回答「这批数字是哪份代码产生的」。

    2026-08-09 实测:它原来只跑 `rev-parse HEAD`,所以从一个带 764 行未提交
    改动的工作区起 run,工件里照样盖一个干净 commit。指纹于是在它唯一该说
    实话的地方说了假话。
    """

    def _repo(self, tmp_path):
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", "-C", str(repo), *a], capture_output=True, check=True)
        run("init", "-q")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", "init")
        return repo

    def test_clean_worktree_reports_the_bare_sha(self, tmp_path):
        from invoiceloop.snapshot import _code_revision

        rev = _code_revision(self._repo(tmp_path))
        assert rev and len(rev) == 40 and not rev.endswith("-dirty")

    def test_uncommitted_change_is_marked_dirty(self, tmp_path):
        from invoiceloop.snapshot import _code_revision

        repo = self._repo(tmp_path)
        (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
        rev = _code_revision(repo)
        assert rev.endswith("-dirty"), \
            "带未提交改动的 run 不许盖一个干净 commit"

    def test_untracked_file_alone_is_not_dirty(self, tmp_path):
        """未跟踪文件不改变**执行的代码**,不算脏 —— 否则 scratch 文件
        会把每一次 run 都标成脏,标记很快就没人看了。"""
        from invoiceloop.snapshot import _code_revision

        repo = self._repo(tmp_path)
        (repo / "scratch.txt").write_text("notes", encoding="utf-8")
        assert not _code_revision(repo).endswith("-dirty")

    def test_outside_a_git_tree_it_says_null_not_a_guess(self, tmp_path):
        from invoiceloop.snapshot import _code_revision

        plain = tmp_path / "plain"
        plain.mkdir()
        assert _code_revision(plain) is None
