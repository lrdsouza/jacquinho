'''How much one message is allowed to carry, and in how many pieces.

She reads on the phone, usually with a pan on the stove. A turn that hands her
the dish, the equipment, the itemised cost, the shopping list, the market band
and the price in one solid block is one she skims, and everything in the middle
is lost. Worse, the question is usually in the middle: the agent asks, she never
sees it, and the next turn opens with a decision she was never given a chance to
make.

Length is not the fault. A long answer to a big question is a good answer. What
fails is stacking: several things she has to decide about, welded into one
paragraph, with the question buried among them.

So this measures **parts**, not size. The turn is split on blank lines, and each
part has to be about one thing, with the question - if there is one - alone in
the last part. The runtime hands her one assistant message per turn, so a part
is a block inside that message; on a gateway that can send more than once, the
same rule produces more than one message and nothing here changes.

The rule itself lives in SOUL.md, and a rule written where it cannot be checked
is advice. This is the check. It never rewrites the message: splitting prose by
rule produces prose that reads split, and the agent already knows where its own
paragraphs end. It says where the seam is, at the one moment the agent is asking
whether the draft is ready - ``confidence_assess_answer``.
'''

from __future__ import annotations

import re

# Subject -> the words that mean the draft is settling that subject. Coarse on
# purpose: a false positive costs one extra paragraph break, a false negative
# costs her the question she never saw.
SUBJECTS: dict[str, tuple[str, ...]] = {
    'prato': ('a receita de', 'esse prato', 'esse é um prato', 'fica ótim',
              'combina bem', 'sai bem no delivery', 'vende bem', 'segura bem'),
    'cozinha': ('tem forno', 'seu forno', 'tem fogão', 'seu fogão',
                'quantas bocas', 'tem panela', 'sua panela', 'tem batedeira',
                'tem liquidificador', 'tem refratário', 'tem uma forma',
                'tem geladeira', 'tem freezer'),
    'custo': ('custa', 'custo', 'sai a r$', 'sai por r$', 'pra você fazer',
              'por marmita fica', 'fecha a conta'),
    'compras': ('precisa comprar', 'vai precisar comprar', 'lista de compras',
                'falta comprar', 'faltam', 'sobrou', 'sobraram',
                'do seu estoque', 'na sua despensa'),
    'orçamento': ('orçamento', 'deixo reservado', 'dos seus r$', 'sobra r$',
                  'sobram r$', 'sobram uns r$'),
    'mercado': ('está saindo', 'estão saindo', 'estão cobrando', 'por aí',
                'concorrên', 'praticam', 'parecida está'),
    'preço': ('quanto quer cobrar', 'quanto você quer cobrar', 'vender por r$',
              'preço de venda', 'você fica com', 'paga pra vender',
              'quanto sobra no seu bolso', 'lucro de'),
}

# One part settles one thing. Two closely related things in one part is still a
# part - the cost and what is missing from it belong together.
MAX_SUBJECTS_PER_PART = 2

# A part she has to hold in her head while reading the next one. Past this it
# stops being a paragraph and becomes a page.
MAX_WORDS_PER_PART = 80

# Below this, stacked nouns are just a sentence with a lot of nouns in it.
MIN_WORDS = 60


def subjects_in(message: str) -> list[str]:
    '''Which of the subjects above this text is trying to settle.'''
    text = (message or '').lower()
    return [name for name, marks in SUBJECTS.items()
            if any(mark in text for mark in marks)]


def questions_in(message: str) -> list[str]:
    '''Every sentence in the text that asks her something.'''
    parts = re.split(r'(?<=[?!.\n])\s+', message or '')
    return [part.strip() for part in parts if part.strip().endswith('?')]


def parts_of(message: str) -> list[str]:
    '''The message as she sees it: one part per line break.

    Any line break, not only a blank one. On her phone a new line is a new
    breath, and that is the unit the rule is about.
    '''
    return [block.strip() for block in (message or '').splitlines() if block.strip()]


def check(message: str) -> dict:
    '''Is this one message per subject, or four welded into one paragraph?

    Returns where the seam is, never a rewrite.
    '''
    blocks = parts_of(message)
    words = len((message or '').split())
    found = subjects_in(message)
    asks = questions_in(message)

    problems = []

    # A wall: several decisions in one unbroken block. This is the failure the
    # rule exists for - not the length, the welding.
    crowded = [
        block for block in blocks
        if len(subjects_in(block)) > MAX_SUBJECTS_PER_PART
        and len(block.split()) >= MIN_WORDS // 2
    ]
    if words >= MIN_WORDS and crowded:
        which = ', '.join(sorted(set(
            subject for block in crowded for subject in subjects_in(block)
        )))
        problems.append(
            f'Uma parte só está resolvendo {which} de uma vez. Quebre: uma coisa '
            'por parte, na ordem em que ela precisa decidir. Tamanho não é o '
            'problema; assunto empilhado é.'
        )

    # And a part can be about one thing and still be a page of it.
    longest = max((len(block.split()) for block in blocks), default=0)
    if longest > MAX_WORDS_PER_PART:
        problems.append(
            f'A maior parte tem {longest} palavras. Ela lê no celular, com a '
            'panela no fogo: quebre em pedaços que cabem numa olhada. O total '
            'pode ser grande; cada parte, não.'
        )

    if len(asks) > 1:
        problems.append(
            f'Tem {len(asks)} perguntas nesta mensagem. Ela responde a primeira '
            'e as outras somem. Deixe uma, e guarde as outras para depois da '
            'resposta dela.'
        )

    if asks and blocks and not blocks[-1].rstrip().endswith('?'):
        problems.append(
            'A pergunta não está no fim. Pergunta no meio é pergunta que ela '
            'não vê: ponha na última parte, sozinha, e espere.'
        )

    return {
        'one_subject_per_part': not problems,
        'parts': len(blocks),
        'subjects': found,
        'questions': asks,
        'words': words,
        'split_because': problems,
        'how_to_split': (
            [
                'Uma parte por assunto, cada uma na sua linha: o prato, depois '
                'a conta, depois o que falta comprar, depois o preço.',
                'A pergunta vai na última parte, sozinha, e aí você espera.',
                'Não anuncie a divisão. Nada de "parte 1 de 3".',
            ]
            if problems else []
        ),
    }
