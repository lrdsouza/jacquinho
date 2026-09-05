"""Unit normalisation: the spreadsheet's packaging traps."""

import pytest

from app.domain.units import Dimension, Package, UnitConverter, UnknownUnitError


@pytest.mark.parametrize(
    'unit, dimension, factor',
    [
        ('kg', Dimension.MASS, 1.0),
        ('L', Dimension.VOLUME, 1.0),
        ('un', Dimension.COUNT, 1.0),
        ('g', Dimension.MASS, 0.001),
        ('ml', Dimension.VOLUME, 0.001),
        ('duzia', Dimension.COUNT, 12.0),
    ],
)
def test_plain_units(unit, dimension, factor):
    package = UnitConverter.parse(unit)
    assert package.dimension == dimension
    assert package.factor == pytest.approx(factor)


@pytest.mark.parametrize(
    'unit, dimension, factor',
    [
        ('balde 2kg', Dimension.MASS, 2.0),
        ('un 500g', Dimension.MASS, 0.5),
        ('un 400g', Dimension.MASS, 0.4),
        ('un 500ml', Dimension.VOLUME, 0.5),
        ('un 100ml', Dimension.VOLUME, 0.1),
    ],
)
def test_packaged_units_carry_their_quantity(unit, dimension, factor):
    """'balde 2kg' is two kilos, not one bucket."""
    package = UnitConverter.parse(unit)
    assert package.dimension == dimension
    assert package.factor == pytest.approx(factor)
    assert package.is_packaged


def test_unknown_unit_raises_rather_than_guessing():
    with pytest.raises(UnknownUnitError):
        UnitConverter.parse('punhado')


def test_empty_unit_raises():
    with pytest.raises(UnknownUnitError):
        UnitConverter.parse('')


def test_accents_and_case_are_irrelevant():
    assert UnitConverter.normalise_text('Açúcar Cristal') == 'acucar cristal'
    assert UnitConverter.normalise_text('Carne moída (patinho)') == 'carne moida patinho'


def test_to_base_converts():
    quantity, unit, dimension = UnitConverter.to_base(200, 'g')
    assert quantity == pytest.approx(0.2)
    assert unit == 'kg'
    assert dimension == Dimension.MASS
