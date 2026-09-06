'''Atomic claims: what a message asserts, one assertion at a time.

The confidence layer scored the *evidence trail* and never looked at the
sentence. The figure audit looked at the sentence and asked one question of each
number: did some tool produce it. Both miss the same thing, and a real
conversation showed it twice: the cost of a dish went out as R$ 9,90, then
R$ 8,18, then R$ 7,15, every figure produced by a tool and every one of them
"grounded". Nothing was asking whether the message contradicted what she had
already been told.

The shape here follows what the fact-checking literature converged on, adapted
to a domain where the evidence is not the open web but this server's own tool
results:

* **Decompose** the message into atomic claims, each one assertion with its own
  subject and value, the way FActScore and VeriScore decompose long-form text.
* **Filter to the verifiable ones**, VeriScore's key correction to FActScore:
  advice, suggestions and questions cannot be right or wrong, and scoring them
  measures the scorer rather than the message.
* **Verify each claim against evidence**, which here is exact, because a price
  either came out of `pricing_price_scenarios` or it did not.
* **Check against commitments**, the multi-turn part: a value stated in an
  earlier turn binds later turns, and the strongest signal is a plain numeric
  mismatch on the same subject and predicate.
* **Allow authorised revision**, so that a number changing *because she asked*
  is not a contradiction. Without this the check would punish the agent for
  doing the right thing.

Extraction is deterministic. The papers use a model for it because they work on
open text about the world; here the world is a handful of tool results, the
vocabulary is fixed, and a regex that cannot hallucinate is worth more than a
second model call per turn.
'''

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field

from .audit import MessageAudit


class ClaimKind(str, Enum):
    '''What a claim is about, which decides how it can be checked.'''

    PANTRY = 'pantry'
    COST = 'cost'
    PRICE = 'price'
    RECEIPT = 'receipt'
    PROFIT = 'profit'
    BUDGET = 'budget'
    MARKET = 'market'
    UNVERIFIABLE = 'unverifiable'


class Verdict(str, Enum):
    GROUNDED = 'grounded'
    UNGROUNDED = 'ungrounded'
    CONTRADICTS = 'contradicts_earlier_turn'
    REVISED = 'revised_because_she_asked'
    NOT_CHECKABLE = 'not_checkable'


# Words that say what a figure is about. The **closest** cue to the figure wins,
# not the first in this list: a window wide enough to catch "vendendo a" also
# catches the "custa" of the previous sentence, and then every number in a
# paragraph inherits the meaning of the first one.
CUES: tuple[tuple[ClaimKind, tuple[str, ...]], ...] = (
    (ClaimKind.PROFIT, ('sobra', 'sobram', 'lucro', 'bolso', 'fica com voce',
                        'fica para voce', 'te sobra', 'de ganho')),
    (ClaimKind.RECEIPT, ('recebe', 'depois da taxa', 'liquido', 'descontada',
                         'descontando')),
    (ClaimKind.BUDGET, ('orcamento', 'reservad', 'reservei', 'restam', 'separad',
                        'comprar', 'compra', 'gastar', 'desembolsa')),
    (ClaimKind.MARKET, ('mercado', 'saindo', 'concorrencia', 'por ai', 'parecida',
                        'referencia')),
    (ClaimKind.COST, ('custa', 'custo', 'cmv', 'sai por', 'ingredientes usados')),
    (ClaimKind.PRICE, ('vend', 'cobrar', 'preco', 'cobra')),
)

# A claim of this kind may hold only one value at a time for a given subject.
# Two different costs for the same dish is a contradiction; two market prices
# is a range.
EXCLUSIVE = {
    ClaimKind.COST, ClaimKind.PRICE, ClaimKind.RECEIPT, ClaimKind.PROFIT,
}


class AtomicClaim(BaseModel):
    '''One assertion, small enough to be true or false on its own.'''

    kind: ClaimKind = Field(description='What the claim is about.')
    subject: str = Field(description='The dish, or the consultation when none.')
    value: float | None = Field(default=None, description='The figure asserted.')
    quoted: str = Field(description='The words the figure appeared in.')
    exclusive: bool = Field(
        default=False,
        description='Whether only one value of this kind may hold at a time.',
    )

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.kind.value)


class CheckedClaim(BaseModel):
    '''A claim with what became of it.'''

    claim: AtomicClaim
    verdict: Verdict
    earlier_value: float | None = None
    note: str = ''

    @property
    def counts(self) -> bool:
        '''Whether this claim participates in the score at all.'''
        return self.verdict is not Verdict.NOT_CHECKABLE

    @property
    def good(self) -> bool:
        return self.verdict in (Verdict.GROUNDED, Verdict.REVISED)


class ClaimExtractor:
    '''Cuts a message into the assertions that can be checked.'''

    # Enough to reach the verb that governs the figure, and short enough that
    # it rarely crosses a sentence boundary on its own.
    WINDOW = 70
    TRAILING_PENALTY = 8

    @classmethod
    def _kind(cls, before: str, after: str) -> ClaimKind:
        '''The cue nearest the figure decides what it is.'''
        left = MessageAudit_normalise(before)
        right = MessageAudit_normalise(after)
        best: tuple[int, ClaimKind] | None = None
        for kind, cues in CUES:
            for cue in cues:
                at = left.rfind(cue)
                if at >= 0:
                    distance = len(left) - (at + len(cue))
                    if best is None or distance < best[0]:
                        best = (distance, kind)
                # A cue after the figure is weaker evidence than one before
                # it: Portuguese puts the governing verb first, as in "custa
                # R$ 4,15" or "vendendo a R$ 24,90". A trailing cue only wins
                # when it is very close, as in "R$ 22,41 depois da taxa".
                at = right.find(cue)
                if at >= 0 and (best is None or at + cls.TRAILING_PENALTY < best[0]):
                    best = (at + cls.TRAILING_PENALTY, kind)
        return best[1] if best else ClaimKind.UNVERIFIABLE

    @classmethod
    def extract(cls, message: str, subject: str) -> list[AtomicClaim]:
        '''Every figure in the message, with what it is asserting.

        A figure inside a question is dropped: "quer vender a R$ 20?" asserts
        nothing, and counting it would mark the agent wrong for asking.
        '''
        claims: list[AtomicClaim] = []
        for figure in MessageAudit.figures(message):
            at = message.find(figure.quoted)
            if at < 0:
                continue
            # Never look past the start of the sentence the figure is in.
            window = message[max(0, at - cls.WINDOW):at]
            cut = max(window.rfind(c) for c in '.!?\n:')
            before = window[cut + 1:] if cut >= 0 else window
            after = message[at + len(figure.quoted):at + len(figure.quoted) + 40]
            if '?' in after.split('.')[0]:
                continue
            kind = cls._kind(before, after)
            claims.append(AtomicClaim(
                kind=kind,
                subject=subject or '(a consultoria)',
                value=round(figure.value, 2),
                quoted=figure.quoted,
                exclusive=kind in EXCLUSIVE,
            ))
        return claims


def MessageAudit_normalise(text: str) -> str:
    '''Lowercase and strip accents, so cue words match how people write.'''
    from .units import UnitConverter

    return UnitConverter.normalise_text(text or '')


class ToolFact(BaseModel):
    """A value a tool established for one dish: the atom, with its identity.

    The identity of a claim comes from **the tool that produced it**, not from
    the words around it in the message. Reading the kind off the prose looked
    reasonable and was not: "sobram R$ 63,91 dos seus R$ 80" is the budget, and
    every cue that makes it profit is also present. A wrong kind is worse than
    no kind, because it invents a contradiction between a profit and a leftover
    that were never about the same thing.
    """

    subject: str
    kind: ClaimKind
    value: float
    source: str = Field(default='', description='Tool and field that produced it.')
    binds: bool = Field(
        default=False,
        description=(
            'Whether this value settles the matter. Three price scenarios are '
            'candidates and bind nothing; the price that went on the menu binds.'
        ),
    )

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.kind.value)


class CommitmentLedger:
    """What she has been told, and is therefore owed consistency about.

    Only values that actually reached her go in here. A cost computed three
    times inside one turn commits to nothing; the one sentence she reads does.
    """

    def __init__(self) -> None:
        self.promised: dict[tuple[str, str], float] = {}
        self.revisions: set[tuple[str, str]] = set()

    def authorise_revision(self, subject: str, kind: ClaimKind | str) -> None:
        """She asked for the change, so the next value is not a contradiction."""
        value = kind.value if isinstance(kind, ClaimKind) else kind
        self.revisions.add((subject, value))

    def ground(self, claim: AtomicClaim, known: set[float]) -> CheckedClaim:
        """Did any tool in this conversation produce this figure?"""
        if claim.value is None:
            return CheckedClaim(claim=claim, verdict=Verdict.NOT_CHECKABLE,
                                note='Não é uma afirmação conferível.')
        if not known or claim.value in {round(v, 2) for v in known}:
            return CheckedClaim(claim=claim, verdict=Verdict.GROUNDED)
        return CheckedClaim(
            claim=claim, verdict=Verdict.UNGROUNDED,
            note='Nenhuma ferramenta produziu esse número nesta conversa.',
        )

    def contradictions(self, facts: list[ToolFact], message: str) -> list[CheckedClaim]:
        """Facts stated in this message that disagree with what she was told.

        A fact only counts as stated when its value literally appears in the
        message: what the tools know and what she knows are different things,
        and only the second one binds.
        """
        said = {round(f.value, 2) for f in MessageAudit.figures(message)}
        out: list[CheckedClaim] = []
        for fact in facts:
            value = round(fact.value, 2)
            if value not in said or fact.kind not in EXCLUSIVE or not fact.binds:
                continue
            earlier = self.promised.get(fact.key)
            if earlier is None or abs(earlier - value) <= 0.005:
                continue
            claim = AtomicClaim(kind=fact.kind, subject=fact.subject, value=value,
                                quoted=f'R$ {value:.2f}'.replace('.', ','),
                                exclusive=True)
            if fact.key in self.revisions:
                out.append(CheckedClaim(
                    claim=claim, verdict=Verdict.REVISED, earlier_value=earlier,
                    note='Ela pediu a mudança, então o valor novo vale.',
                ))
                continue
            out.append(CheckedClaim(
                claim=claim, verdict=Verdict.CONTRADICTS, earlier_value=earlier,
                note=(
                    f'Ela ouviu R$ {earlier:.2f} de {LABEL[fact.kind]} para '
                    f'{fact.subject!r}, e agora ouviu R$ {value:.2f}, sem '
                    'ninguém dizer que mudou.'
                ),
            ))
        return out

    def bind(self, facts: list[ToolFact], message: str) -> list[ToolFact]:
        """What she just heard becomes the promise, and nothing else does."""
        said = {round(f.value, 2) for f in MessageAudit.figures(message)}
        bound = []
        for fact in facts:
            value = round(fact.value, 2)
            if fact.binds and fact.kind in EXCLUSIVE and value in said:
                self.promised[fact.key] = value
                self.revisions.discard(fact.key)
                bound.append(fact)
        return bound


LABEL = {
    ClaimKind.PANTRY: 'despensa',
    ClaimKind.COST: 'custo',
    ClaimKind.PRICE: 'preço',
    ClaimKind.RECEIPT: 'o que ela recebe',
    ClaimKind.PROFIT: 'lucro',
    ClaimKind.BUDGET: 'orçamento',
    ClaimKind.MARKET: 'mercado',
    ClaimKind.UNVERIFIABLE: 'afirmação',
}


class ClaimPipeline:
    """The whole check, in the order the literature settled on.

    Decompose, drop what cannot be checked, verify each remaining claim against
    the evidence, compare against what she was already told, then bind this
    message as the new promise. Deterministic end to end: no model call, so it
    runs on every single turn without a budget conversation.
    """

    @staticmethod
    def run(
        message: str,
        subject: str,
        known_numbers: set[float],
        facts: list['ToolFact'],
        ledger: 'CommitmentLedger',
    ) -> 'MessageJudgement':
        claims = ClaimExtractor.extract(message, subject)
        checked = [ledger.ground(claim, known_numbers) for claim in claims]
        clashes = ledger.contradictions(facts, message)

        # A contradiction supersedes the grounding verdict for the same figure:
        # a number can be perfectly grounded and still be the wrong one to say.
        clashing = {c.claim.value for c in clashes}
        checked = [c for c in checked if c.claim.value not in clashing] + clashes

        judgement = MessageJudgement.of(checked)
        ledger.bind(facts, message)
        return judgement


class MessageJudgement(BaseModel):
    '''The confidence of one message, built from its claims.'''

    claims: list[CheckedClaim]
    verifiable: int
    grounded: int
    contradictions: int
    ungrounded: int
    score: float
    verdict: str

    @classmethod
    def of(cls, checked: list[CheckedClaim]) -> 'MessageJudgement':
        checkable = [c for c in checked if c.counts]
        good = [c for c in checkable if c.good]
        contra = [c for c in checkable if c.verdict is Verdict.CONTRADICTS]
        loose = [c for c in checkable if c.verdict is Verdict.UNGROUNDED]

        # A message with nothing to check is not suspicious; it is a question,
        # or a suggestion, and 1.00 says "nothing here can be wrong".
        score = len(good) / len(checkable) if checkable else 1.0
        # One contradiction sinks the message. Being told two different costs
        # is not eighty percent fine.
        if contra:
            score = 0.0
        return cls(
            claims=checked,
            verifiable=len(checkable),
            grounded=len(good),
            contradictions=len(contra),
            ungrounded=len(loose),
            score=round(score, 2),
            verdict=(
                'contradiz o que ela já ouviu' if contra
                else 'cifra sem lastro' if loose
                else 'tudo confere' if checkable
                else 'nada a conferir'
            ),
        )
