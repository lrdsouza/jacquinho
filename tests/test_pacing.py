"""One part per subject, and the question alone at the end.

The failure this checks for is not length - it is a turn that settles the dish,
the cost, the shopping and the price welded into one block, with the question
buried where she never sees it. 'Não importa ser grande.'
"""

from app.domain.pacing import check, parts_of, questions_in, subjects_in

WALL = (
    'A receita de lasanha de panela fica ótima e segura bem no delivery. '
    'Cada marmita custa R$ 7,53 pra você fazer, com 100 g de carne moída, '
    '50 g de mussarela e o molho. Você vai precisar comprar a massa por '
    'R$ 6,95, e sobram R$ 73,05 dos seus R$ 80 de orçamento. Marmita '
    'parecida está saindo entre R$ 16 e R$ 26 por aí, então dá para vender '
    'por R$ 19,90 com folga e você fica com uns R$ 10,38 em cada uma. '
    'Quanto você quer cobrar?'
)

PARTED = (
    'A receita de lasanha de panela fica ótima e segura bem no delivery.\n'
    'Cada marmita custa R$ 7,53 pra você fazer: 100 g de carne moída '
    '(R$ 2,80), 50 g de mussarela (R$ 2,00) e o resto do molho.\n'
    'Você vai precisar comprar a massa, uns R$ 6,95. Isso deixa R$ 73,05 '
    'dos seus R$ 80.\n'
    'Marmita parecida está saindo entre R$ 16 e R$ 26 por aí.\n'
    'Quanto você quer cobrar?'
)


def test_the_same_words_pass_once_they_are_in_parts():
    """Length is not the problem. Welding is."""
    assert check(WALL)['one_subject_per_part'] is False
    assert check(PARTED)['one_subject_per_part'] is True
    assert check(PARTED)['parts'] == 5
    assert check(PARTED)['words'] > 60


def test_a_long_answer_about_one_thing_is_fine():
    """She asked what it costs, and the whole answer is what it costs."""
    message = (
        'A lasanha de panela leva 100 g de carne moída, 50 g de mussarela, '
        'meia caixa de molho de tomate e a massa.\n'
        'Cada marmita custa R$ 7,53: a carne é R$ 2,80, a mussarela R$ 2,00, '
        'a massa R$ 1,62 e o resto do molho fecha a conta.'
    )
    report = check(message)
    assert report['one_subject_per_part'] is True
    assert report['subjects'] == ['custo']


def test_a_part_can_be_about_one_thing_and_still_be_a_page_of_it():
    wordy = 'A conta dessa fornada ' + 'olha só que detalhe interessante ' * 20
    assert any('palavras' in why for why in check(wordy)['split_because'])


def test_two_questions_in_one_message_lose_the_second():
    message = (
        'Antes de fechar a conta da fornada inteira preciso de duas coisas.\n'
        'Você tem uma panela grande com tampa? E o seu fogão é a gás ou '
        'elétrico, quantas bocas?'
    )
    report = check(message)
    assert len(report['questions']) == 2
    assert any('perguntas' in why for why in report['split_because'])


def test_a_question_before_the_last_part_is_a_question_she_does_not_see():
    message = (
        'Você tem uma panela grande com tampa?\n'
        'Enquanto isso eu já vou adiantando a conta da fornada para você.'
    )
    assert any('fim' in why for why in check(message)['split_because'])


def test_a_question_alone_at_the_end_is_fine():
    message = 'A lasanha de panela leva massa, carne e queijo.\nVocê tem panela grande?'
    assert check(message)['one_subject_per_part'] is True


def test_a_short_message_is_never_a_wall():
    """Two nouns in one sentence is a sentence, not four messages."""
    report = check('O custo sai R$ 7,53 e por aí a marmita está saindo R$ 19,90.')
    assert report['one_subject_per_part'] is True


def test_the_seam_is_named_so_the_agent_knows_where_to_cut():
    why = check(WALL)['split_because'][0]
    assert 'custo' in why and 'preço' in why
    assert check(WALL)['how_to_split']


def test_a_part_is_what_she_sees_on_the_screen():
    """Any line break, not only a blank one: a new line is a new breath."""
    assert parts_of('uma\ndois\n\ntrês') == ['uma', 'dois', 'três']


def test_the_subjects_are_the_decisions_not_every_noun():
    """'Quando for ao mercado' is not a market reference, and a pan mentioned
    in a recipe is not a question about her kitchen."""
    assert subjects_in('confira quando for ao mercado, na lasanha de panela') == []
    assert 'custo' in subjects_in('cada marmita custa R$ 7,53')
    assert 'compras' in subjects_in('você vai precisar comprar a massa')
    assert questions_in('Tudo certo. Quer seguir?') == ['Quer seguir?']
