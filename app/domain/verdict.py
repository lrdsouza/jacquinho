'''The verdict she is owed, and the check that it actually reached her.

The gate worked long before this module existed: the server knew the lasanha
was dead the moment she said she had no oven. What it could not do was make the
agent *say so*. Three rounds of stronger wording in tool results - a next_step
spelling out the sentence, then the sentence returned ready to paste - all lost
to the same failure: the model files the answer, respects it from then on, and
replies about something else. She gave up the fact that killed her dish and
heard nothing about her dish.

Wording cannot fix that, because wording is advice. What can is making the
verdict a debt the session owes, refusing every tool that means 'moving on'
while the debt is open, and settling it only through a call that carries the
words she will actually read - checked here for the two things that make them
an answer rather than an acknowledgement: her dish, by name, and what stopped
it (or what brought it back).
'''

from __future__ import annotations

from .units import UnitConverter

RULED_OUT = 'ruled_out'
BACK_ON = 'back_on'


class VerdictAnnouncement:
    '''Checks that a sentence really tells her what happened to her dish.'''

    # Enough to be a sentence. 'Ok' and 'entendido' are acknowledgements to the
    # tool, not answers to her.
    MIN_WORDS = 8

    STOP_WORDS = frozenset({
        'de', 'da', 'do', 'das', 'dos', 'em', 'com', 'e', 'a', 'o', 'as', 'os',
        'ao', 'aos', 'na', 'no', 'nas', 'nos', 'um', 'uma', 'que', 'para',
        'pra', 'por', 'sem', 'the', 'of',
    })

    @classmethod
    def _words(cls, text: str) -> list[str]:
        return [w for w in UnitConverter.normalise_text(text or '').split() if w]

    @classmethod
    def _significant(cls, text: str) -> list[str]:
        return [
            word for word in cls._words(text)
            if len(word) > 2 and word not in cls.STOP_WORDS
        ]

    @classmethod
    def _mentions(cls, said: set[str], phrase: str) -> bool:
        '''True when the sentence carries at least one meaningful word of the
        phrase. 'a lasanha' counts for 'lasanha ao forno': she calls her own
        dish by its short name and so should the agent.'''
        wanted = cls._significant(phrase)
        return any(word in said for word in wanted) if wanted else True

    @classmethod
    def check(cls, message: str, dish: str, items: list[str]) -> dict:
        '''Does this sentence tell her what happened, and why?'''
        words = cls._words(message)
        said = set(words)
        missing: list[str] = []

        if len(words) < cls.MIN_WORDS:
            missing.append('uma frase inteira, não um aceno')
        # 'lasanha ao forno' shares a word with the thing that blocks it, so
        # naming the oven would otherwise count as naming the dish. Strip the
        # overlap first: what is left is what actually identifies HER dish.
        blocking_words = {w for item in items for w in cls._significant(item)}
        own = [w for w in cls._significant(dish) if w not in blocking_words]
        if dish and own and not any(word in said for word in own):
            missing.append(f'o nome do prato dela ({dish})')
        for item in items:
            if not cls._mentions(said, item):
                missing.append(f'o que decidiu isso ({item})')

        return {'ok': not missing, 'missing': missing, 'word_count': len(words)}

    @classmethod
    def for_block(cls, dish: str, blockers: list[str]) -> dict:
        travas = ', '.join(blockers)
        return {
            'kind': RULED_OUT,
            'dish': dish,
            'items': list(blockers),
            'say_now': (
                f'Ela ainda não ouviu que {dish} está fora por falta de {travas}. '
                'Diga isso a ela agora, com todas as letras, e ofereça uma versão '
                'do prato DELA que caiba na cozinha que ela tem. Depois registre '
                'a frase em kitchen_announce_verdict - até lá, nada de mudar de '
                'assunto.'
            ),
        }

    @classmethod
    def for_unblock(cls, dishes: list[str], capability: str) -> dict:
        nomes = ', '.join(dishes)
        return {
            'kind': BACK_ON,
            'dish': dishes[0] if dishes else '',
            'dishes': list(dishes),
            'items': [capability],
            'say_now': (
                f'Agora que ela tem {capability}, {nomes} voltou para a mesa e ela '
                'ainda não sabe. Conte a ela, dizendo que foi o que faltava antes, '
                'e registre a frase em kitchen_announce_verdict.'
            ),
        }
