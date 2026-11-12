"""Advisory copy checks shared by HTML and native slide audits."""


def flagged_phrases(text: str) -> list[str]:
    # The source or a named framework may use these words intentionally.
    phrases = ("关键抓手", "形成飞轮", "复利化", "全面赋能", "闭环放大")
    return [phrase for phrase in phrases if phrase in text]
