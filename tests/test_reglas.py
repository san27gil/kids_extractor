from kid_extractor import reglas

# El porcentaje que aparece tiene que descartarlo porque no es TER
def test_leer_ter_no_confunde_costes_operacion():
    texto = ("Comisiones de gestión y otros gastos administrativos u operativos "
             "Gastos de transacción 0.09 % Es una estimación de los costes incurridos en la compra y venta de las inversiones subyacentes del producto. El importe efectivo variará en función de la cantidad de compras y ventas que se realicen.")
    assert reglas.leer_ter(texto) is None

# Riesgo lo coge bien
def test_leer_sri():
    texto = "En una escala de 1 a 7, la categoría de riesgo de este producto se establece en 2, que representa un riesgo bajo."
    assert reglas.leer_sri(texto) == 2

# TER lo lee bien
def test_leer_ter():
    texto = "Comisiones de gestión y otros gastos administrativos u operativos 0.47 % Es una estimación basada en los costes reales del último año. "
    assert reglas.leer_ter(texto) == 0.47

# Un TER mayor a 5 tiene que descartarlo
def test_leer_ter_mas_de_5():
    texto = "Comisiones de gestión y otros gastos administrativos u operativos 5.47 % Es una estimación basada en los costes reales del último año. "
    assert reglas.leer_ter(texto) is None

# Lee bien los ISIN
def test_leer_isins():
    texto = 'PRODUCTO Nombre de producto: Evli Corporate Bond Fund ("Fondo") Nombre del promotor del producto PRIIP: Evli Fund Management Company Ltd (la "Sociedad Gestora del Fondo"), que forma parte del Grupo Evli. ISIN: FI4000243217, Serie de participaciones IB.'
    assert reglas.leer_isins(texto) == ["FI4000243217"]

def test_isin_valido():
    assert reglas.isin_valido("FI4000243217")
    assert not reglas.isin_valido("FI4000243218")