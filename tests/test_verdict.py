"""The sentence she actually reads, checked for the two things that make it one.

These need no database and no server: it is string work, which is exactly why
it can be trusted to run on every change.
"""

from app.domain.verdict import BACK_ON, RULED_OUT, VerdictAnnouncement


def test_a_real_answer_passes():
    check = VerdictAnnouncement.check(
        'A lasanha ao forno fica fora porque precisa de forno e voce so tem o '
        'cooktop, mas da pra fazer lasanha de panela',
        'lasanha ao forno', ['forno'],
    )
    assert check['ok']
    assert check['missing'] == []


def test_an_acknowledgement_is_not_an_answer():
    """'Entendido' is addressed to the tool, not to her."""
    check = VerdictAnnouncement.check('Ok, entendido', 'lasanha ao forno', ['forno'])
    assert not check['ok']
    assert any('frase inteira' in miss for miss in check['missing'])


def test_changing_the_subject_politely_is_still_changing_the_subject():
    check = VerdictAnnouncement.check(
        'Vou procurar outras opcoes que combinem melhor com a sua cozinha hoje',
        'lasanha ao forno', ['forno'],
    )
    assert not check['ok']
    assert any('nome do prato' in miss for miss in check['missing'])


def test_naming_the_blocker_does_not_count_as_naming_the_dish():
    """'lasanha ao forno' shares a word with what blocks it. Saying only 'forno'
    would otherwise pass for having named her dish."""
    check = VerdictAnnouncement.check(
        'Voce nao tem forno entao esse prato nao vai dar certo aqui em casa',
        'lasanha ao forno', ['forno'],
    )
    assert not check['ok']
    assert any('nome do prato' in miss for miss in check['missing'])


def test_the_short_name_counts():
    """She calls her own dish 'a lasanha', and so should the agent."""
    check = VerdictAnnouncement.check(
        'A lasanha sai do cardapio: ela precisa de forno e voce so tem cooktop',
        'lasanha ao forno', ['forno'],
    )
    assert check['ok']


def test_the_reason_has_to_be_there():
    check = VerdictAnnouncement.check(
        'A lasanha nao vai dar certo por enquanto, vamos pensar em outra coisa',
        'lasanha ao forno', ['forno'],
    )
    assert not check['ok']
    assert any('decidiu isso' in miss for miss in check['missing'])


def test_every_blocker_has_to_be_named():
    check = VerdictAnnouncement.check(
        'A lasanha sai porque precisa de forno e voce nao tem',
        'lasanha ao forno', ['forno', 'batedeira'],
    )
    assert not check['ok']
    assert any('batedeira' in miss for miss in check['missing'])


def test_the_block_announcement_names_dish_and_blocker():
    owed = VerdictAnnouncement.for_block('lasanha ao forno', ['forno'])
    assert owed['kind'] == RULED_OUT
    assert owed['items'] == ['forno']
    assert 'lasanha ao forno' in owed['say_now']
    assert 'announce_verdict' in owed['say_now']


def test_the_comeback_announcement_says_what_changed():
    owed = VerdictAnnouncement.for_unblock(['lasanha ao forno'], 'forno')
    assert owed['kind'] == BACK_ON
    assert 'forno' in owed['say_now']
    assert 'lasanha ao forno' in owed['say_now']
