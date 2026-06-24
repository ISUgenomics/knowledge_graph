from .base import ChatModule


class PeopleChatModule(ChatModule):
    def corpus_section(self) -> str | None:
        return "people"
