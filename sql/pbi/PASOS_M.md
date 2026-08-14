# Pasos M para Power Query

Uno por tabla del modelo, generado desde las vistas de `pbi_bnpl`.

**Reemplazar el paso `Origen` completo por esto, y no dejar nada después.** En particular hay
que borrar `Table.TransformColumnTypes` y `Table.RemoveColumns`: las vistas ya devuelven el tipo
correcto y no traen la columna sin nombre que traía el CSV, así que esos dos pasos fallan.

El M no vuelve a cambiar aunque se corrija una consulta: la lógica vive en `sql/pbi/*.sql` y
`build_bnpl.py` reconstruye la vista en cada corrida.

> **El esquema siempre va calificado.** `grid_bnpl` y `vintage_analysis` existen también en el
> esquema `bnpl`, con los nombres en snake_case. Conectar el equivocado no falla al cargar:
> falla después, en cada medida DAX que busque `grid_bnpl[netsuiteId]`, y además reescribe las
> relaciones apuntando a `netsuite_id`.

Ver también: [agregar una tabla nueva](README.md#agregar-una-tabla-nueva-al-tablero) ·
[cuando falla el refresh](README.md#cuando-falla-el-refresh). Al agregar una tabla, agrega aquí su
paso M y su renglón en la tabla de abajo.

Filas y columnas verificadas contra la base el 2026-08-14.

| Tabla del modelo | Filas | Cols |
|---|---|---|
| `atr_combinations_iv` | 468 | 5 |
| `bnpl_audiencia_agg` | 214 | 5 |
| `bnpl_cac` | 25 | 2 |
| `bnpl_cosechas_agg` | 51,721 | 11 |
| `bnpl_grouped_orders` | 99,019 | 31 |
| `bnpl_loss_rates` | 92,009 | 37 |
| `bnpl_par` | 1,061,120 | 32 |
| `concurso_base` | 1,098 | 44 |
| `grid_bnpl` | 146,542 | 55 |
| `loans_matured_default_profile` | 90,262 | 50 |
| `months_closes` | 1,061,120 | 31 |
| `odds_combinations` | 84,986 | 15 |
| `odds_table` | 18 | 14 |
| `overall_prev_post_bnpl_sales` | 1,293,358 | 22 |
| `ps_transactional_profile` | 100,793 | 2 |
| `seasonality_delta` | 132 | 10 |
| `vars_and_iv` | 6 | 4 |
| `vintage_analysis` | 530 | 21 |

---

## atr_combinations_iv

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.atr_combinations_iv", null, [EnableFolding=true])
in
    Origen
```

## bnpl_audiencia_agg

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_audiencia_agg", null, [EnableFolding=true])
in
    Origen
```

## bnpl_cac

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_cac", null, [EnableFolding=true])
in
    Origen
```

## bnpl_cosechas_agg

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_cosechas_agg", null, [EnableFolding=true])
in
    Origen
```

## bnpl_grouped_orders

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_grouped_orders", null, [EnableFolding=true])
in
    Origen
```

## bnpl_loss_rates

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_loss_rates", null, [EnableFolding=true])
in
    Origen
```

## bnpl_par

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.bnpl_par", null, [EnableFolding=true])
in
    Origen
```

## concurso_base

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.concurso_base", null, [EnableFolding=true])
in
    Origen
```

## grid_bnpl

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.grid_bnpl", null, [EnableFolding=true])
in
    Origen
```

## loans_matured_default_profile

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.loans_matured_default_profile", null, [EnableFolding=true])
in
    Origen
```

## months_closes

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.months_closes", null, [EnableFolding=true])
in
    Origen
```

## odds_combinations

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.odds_combinations", null, [EnableFolding=true])
in
    Origen
```

## odds_table

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.odds_table", null, [EnableFolding=true])
in
    Origen
```

## overall_prev_post_bnpl_sales

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.overall_prev_post_bnpl_sales", null, [EnableFolding=true])
in
    Origen
```

## ps_transactional_profile

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.ps_transactional_profile", null, [EnableFolding=true])
in
    Origen
```

## seasonality_delta

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.seasonality_delta", null, [EnableFolding=true])
in
    Origen
```

## vars_and_iv

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.vars_and_iv", null, [EnableFolding=true])
in
    Origen
```

## vintage_analysis

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.vintage_analysis", null, [EnableFolding=true])
in
    Origen
```
