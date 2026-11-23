import unittest

import notifier
from notifier import PushService, html_to_lark_md, _safe_url


class TestMarkupConversion(unittest.TestCase):
    def test_lark_md_uses_markdown_bold(self):
        body = "👤 <b>呼号</b>: BG5ABC (SMITH &amp; SONS)"
        out = html_to_lark_md(body)
        self.assertIn("**呼号**", out)
        self.assertIn("SMITH & SONS", out)
        self.assertNotIn("&amp;", out)
        self.assertNotIn("<b>", out)

    def test_user_supplied_tag_stays_literal(self):
        # A value containing "<b>" arrives escaped; it must stay text, not become bold
        # 值里的 <b> 到达时已转义，转换后应仍是普通文本而不是加粗标签
        self.assertEqual(html_to_lark_md("x <b>y</b> &lt;b&gt;"),
                         "x **y** <b>")

    def test_safe_url_masks_bot_token(self):
        url = _safe_url("https://api.telegram.org/bot123456:AAH-secret/sendMessage")
        self.assertNotIn("123456:AAH-secret", url)
        self.assertIn("sendMessage", url)

    def test_safe_url_keeps_plain_urls(self):
        url = "https://www.pushplus.plus/send"
        self.assertEqual(_safe_url(url), url)

    def test_safe_url_masks_feishu_hook_id(self):
        url = "https://open.feishu.cn/open-apis/bot/v2/hook/abc-secret-id"
        masked = _safe_url(url)
        self.assertNotIn("abc-secret-id", masked)
        self.assertIn("/hook/***", masked)

    def test_safe_url_masks_hook_id_with_trailing_slash(self):
        # A copied webhook often ends with '/'; rpartition('/') used to leave
        # the credential fully visible in every failure log line.
        url = "https://open.feishu.cn/open-apis/bot/v2/hook/abc-secret-id/"
        masked = _safe_url(url)
        self.assertNotIn("abc-secret-id", masked)
        self.assertIn("/hook/***/", masked)


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "push_fs_enabled": True, "fs_webhook": "https://open.feishu.cn/x", "fs_secret": "",
            "push_wx_enabled": False, "wx_token": "",
            "push_tg_enabled": False, "tg_token": "", "tg_chat_id": "",
        }
        self._orig_feishu = PushService._push_feishu
        self._orig_wechat = PushService._push_wechat
        self._orig_telegram = PushService._push_telegram
        self._orig_queue = notifier.PUSH_MAX_QUEUE

    def tearDown(self):
        PushService._push_feishu = self._orig_feishu
        PushService._push_wechat = self._orig_wechat
        PushService._push_telegram = self._orig_telegram
        notifier.PUSH_MAX_QUEUE = self._orig_queue

    def test_all_channels_failing_reports_failure(self):
        PushService._push_feishu = classmethod(lambda cls, *a, **k: False)
        before = PushService.stats()
        ok = PushService._do_push_logic(self.cfg, "t", "b", True)
        self.assertFalse(ok)
        after = PushService.stats()
        self.assertEqual(after["failed"], before["failed"] + 1)
        self.assertTrue(after["recent_failures"])
        self.assertIn("feishu", after["recent_failures"][-1]["channel"])

    def test_single_success_wins(self):
        PushService._push_feishu = classmethod(lambda cls, *a, **k: False)
        self.cfg["push_wx_enabled"] = True
        self.cfg["wx_token"] = "x" * 32
        PushService._push_wechat = classmethod(lambda cls, *a, **k: True)
        self.assertTrue(PushService._do_push_logic(self.cfg, "t", "b", True))

    def test_no_channel_is_skipped(self):
        cfg = {"push_fs_enabled": False, "push_wx_enabled": False, "push_tg_enabled": False}
        before = PushService.stats()
        self.assertFalse(PushService._do_push_logic(cfg, "t", "b", True))
        self.assertEqual(PushService.stats()["skipped"], before["skipped"] + 1)

    def test_queue_full_drops_instead_of_growing(self):
        notifier.PUSH_MAX_QUEUE = 0
        before = PushService.stats()
        self.assertIsNone(PushService.send(self.cfg, "t", "b", True, async_mode=True))
        self.assertEqual(PushService.stats()["dropped"], before["dropped"] + 1)

    def test_sync_mode_returns_bool(self):
        PushService._push_feishu = classmethod(lambda cls, *a, **k: True)
        self.assertIs(PushService.send(self.cfg, "t", "b", True, async_mode=False), True)


class TestTlsPolicy(unittest.TestCase):
    """Certificate errors must be classified, and downgrade must be opt-out-able"""

    def setUp(self):
        import ssl as _ssl
        import urllib.error
        self._orig_open = notifier.urllib.request.urlopen
        self.calls = []

        def _raise_cert(*args, **kwargs):
            self.calls.append(kwargs.get("context"))
            exc = _ssl.SSLCertVerificationError(1, "certificate verify failed")
            raise urllib.error.URLError(exc)

        notifier.urllib.request.urlopen = _raise_cert
        self._orig_uses = PushService._insecure_uses

    def tearDown(self):
        notifier.urllib.request.urlopen = self._orig_open
        PushService._insecure_uses = self._orig_uses

    def test_wrapped_cert_error_is_detected_as_tls(self):
        state, _body = PushService._attempt("https://example.org/x", b"", False, None)
        self.assertEqual(state, "tls")

    def test_no_downgrade_when_disabled(self):
        ok, _ = PushService._http_post("https://api.telegram.org/botX/sendMessage",
                                       data=b"", allow_insecure=False)
        self.assertFalse(ok)
        self.assertEqual(len(self.calls), 1, "must not retry with an unverified context")

    def test_downgrade_counts_and_retries_when_allowed(self):
        before = PushService._insecure_uses
        ok, _ = PushService._http_post("https://www.pushplus.plus/send", data=b"", retries=0)
        self.assertFalse(ok)
        self.assertEqual(len(self.calls), 2, "verified attempt + one insecure retry")
        self.assertEqual(PushService._insecure_uses, before + 1)


if __name__ == '__main__':
    unittest.main()
