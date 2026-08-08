# Modelo conceptual y diagrama de procesos

Cómo la solución analítica aporta a los objetivos del negocio y cómo sus
resultados entran en los procesos de CREAN: flujos de información, actores y
puntos de decisión.

---

## 1. El problema, en términos conceptuales

CREAN necesita responder dos preguntas antes de lanzar la App:

1. **¿Quién adoptaría?** — priorización comercial.
2. **¿Cuánto volumen se canalizaría?** — dimensionamiento de la oportunidad.

La dificultad de fondo es que **la App todavía no existe**, así que no hay
adopciones que observar. La solución construye una **etiqueta proxy**: se
considera "adoptante" a quien hoy tiene saldo activo en **Invesbot** o
**Inversión Virtual**, los dos productos digitales de inversión que más se
parecen a la App. Esa decisión es el supuesto que sostiene todo lo demás, y es
también lo primero que caduca cuando la App salga a producción (ver
[esquema de operación](esquema_operacion.md), sección de evolución).

### Los objetivos de negocio y el aporte de la solución

Antes de describir cómo funciona, conviene fijar contra qué se mide. Cada fila
es un objetivo del negocio, no una capacidad técnica, y la última columna es lo
que hoy está medido — no lo que se espera.

| Objetivo de negocio | Cómo aporta la solución | Evidencia medida |
|---|---|---|
| Lanzar la App con una meta sustentada | Dimensiona el volumen con el supuesto a la vista | 1,86 billones COP de entrada bruta; **186 / 465 / 744** mil M según la tasa de captura que asuma el negocio |
| Concentrar el esfuerzo comercial | Ordena por propensión dentro de cada población | Contactar el **10%** mejor rankeado alcanza al **51,2%** de los adoptantes: 5,1× la tasa base |
| No dejar clientes fuera del análisis | Puntúa al 100% de la base, no solo a quien ya invierte | **860.223** clientes con score, cero nulos |
| Activar a quien ya es cliente | Aísla a quien tiene productos pero ninguno de inversión | **309.928** clientes: uso no realizado, no adquisición |
| Retener saldo que se está yendo | Identifica la salida proyectada, no solo la entrada | **40.137** clientes, −0,76 billones COP |
| Decidir con evidencia, no con opinión | Declara y mide cada supuesto | 64 variables validadas estadísticamente; log de decisiones *append-only* |
| Operar sin riesgo reputacional | Audita el sesgo antes de que la lista se use | Regla del 80% por atributo protegido; proxy de género 0,625 (moderado) |

Dos de estas filas merecen subrayarse porque **no estaban en el encargo** y
salieron del mismo modelo: la población de activación y el bloque de retención.
El encargo pedía a quién ofrecerle la App; el modelo, al proyectar el cambio de
saldo, también señala a quién se está por perder.

De ahí se derivan tres conceptos que estructuran la solución entera:

| Concepto | Qué es | Por qué existe |
|---|---|---|
| **Población** | Partición de la base según qué evidencia hay del cliente | No se le puede pedir lo mismo a un cliente sin productos que a uno que ya invierte |
| **Propensión** | Ordenamiento por probabilidad (o similitud) de adoptar | Responde "a quién" |
| **Monto potencial** | Proyección del cambio de saldo invertido a 12 meses | Responde "cuánto" |

### Las tres poblaciones son tres estrategias

La partición no es una tecnicalidad de modelado: cada población admite una
acción comercial distinta y **solo una de las tres permite estimar monto**.

```mermaid
flowchart LR
    B["Base del banco<br/>860.223 clientes"]

    B --> P1["Sin ningún producto<br/>330.753"]
    B --> P2["Con productos,<br/>sin inversión<br/>309.928"]
    B --> P3["Con inversión previa<br/>219.542"]

    P1 --> E1["ADQUISICIÓN<br/>Modelo B · similitud<br/>Monto: no estimable"]
    P2 --> E2["ACTIVACIÓN<br/>Modelo A · probabilidad<br/>Monto: no estimable"]
    P3 --> E3["CRECIMIENTO<br/>Modelo A · probabilidad<br/>Monto: estimado"]

    style P1 fill:#E8F1F5,stroke:#1F6F8B
    style P2 fill:#E8F1F5,stroke:#1F6F8B
    style P3 fill:#E6F2EC,stroke:#2E8B57
    style E3 fill:#E6F2EC,stroke:#2E8B57
```

**Por qué el monto solo se estima en la tercera**: proyectar un saldo requiere
una serie histórica de ese saldo. Quien nunca ha invertido no tiene sobre qué
extrapolar. Para esas dos poblaciones el monto es **nulo, no cero** — es
desconocido, no es ausencia de oportunidad.

**Por qué la primera usa un modelo distinto**: un cliente sin ningún producto
tiene etiqueta de adopción 0 *por construcción* (no puede tener saldo en
Invesbot si no tiene productos). No existen positivos contra los cuales
validar una probabilidad, así que el Modelo B entrega un **puntaje de
similitud** — cuánto se parece a quien sí adoptó — y no una probabilidad.
Es una distinción que hay que sostener frente al negocio: ese número no se
puede presentar como tasa de conversión esperada.

---

## 2. Modelo conceptual de datos

Siete fuentes operativas se integran en una arquitectura medallón hasta
producir una vista única por cliente y un esquema estrella para consumo
analítico.

```mermaid
flowchart TD
    subgraph FUENTES["7 fuentes operativas"]
        F1["Clientes<br/>sociodemográfico + financiero"]
        F2["Ahorros y Corriente"]
        F3["Bolsillos"]
        F4["Fiducuenta"]
        F5["CDT e Inversión Virtual"]
        F6["Invesbot"]
        F7["Estimador de ingresos"]
    end

    FUENTES --> BR["<b>BRONCE</b><br/>Ingesta cruda, sin transformar<br/>+ diagnóstico de calidad"]
    BR --> PL["<b>PLATA</b><br/>Limpieza, deduplicación,<br/>agregación por cliente-producto,<br/>panel mensual con forward-fill"]
    PL --> OR["<b>ORO</b><br/>cliente_features · 1 fila por cliente<br/>+ esquema estrella"]

    OR --> M1["Modelo de propensión"]
    OR --> M2["Modelo de monto 12m"]
    M1 --> SC["<b>fact_cliente_score</b><br/>score · nivel · población<br/>monto · valor de referencia"]
    M2 --> SC

    SC --> C1["Tablero Streamlit"]
    SC --> C2["Power BI"]
    SC --> C3["Lista de contacto CSV"]
    SC --> C4["Vitrina web<br/>Cloudflare Workers + D1"]

    style BR fill:#F5E9D7,stroke:#B08D57
    style PL fill:#ECEFF1,stroke:#78909C
    style OR fill:#FBF3DC,stroke:#D9A441
    style SC fill:#E6F2EC,stroke:#2E8B57
```

**Granularidad y trazabilidad**, que es lo que el requerimiento pide garantizar:

| Capa | Grano | Consistencia de identificadores |
|---|---|---|
| Bronce | El de origen (transaccional/diario) | `numero_id` sin tocar; 860.231 filas con 860.223 IDs únicos |
| Plata | Cliente-producto, más panel cliente-mes | Deduplicación explícita; ningún cliente se pierde |
| Oro | **Una fila por cliente** (860.223) | Clave única verificada por test |

Toda variable que entra a un modelo queda registrada en
`outputs/eda/validacion_variables.csv` con su poder predictivo, su
significancia estadística y la decisión de incluirla o descartarla. Toda
decisión de negocio queda en `outputs/decisiones/log_decisiones.csv` con su
motivo y su evidencia medida.

---

## 3. Diagrama de procesos: flujos, actores y decisiones

### 3.1 Quién interviene

Seis actores. La columna que más importa es la tercera: **qué decide cada uno**,
porque delimita dónde termina el modelo y dónde empieza el criterio del negocio.

| Actor | Qué recibe | Qué decide | Qué entrega |
|---|---|---|---|
| **TI / Plataforma** | — | Nada del proceso analítico | Extractos mensuales de las 7 fuentes |
| **Analítica** | Los extractos | Qué variable entra al modelo · si hay fuga · si se reentrena | Score, nivel, monto y auditoría |
| **Riesgo y Cumplimiento** | Informe de sesgo | **Si la lista se puede operar** | Visto bueno, o hallazgo documentado |
| **CREAN / Producto** | Dimensionamiento | **La tasa de captura que se asume** | Meta de lanzamiento |
| **Comercial** | Lista priorizada | Hasta qué percentil se contacta | Resultado real de contacto |
| **Dirección** | Meta y su supuesto | Inversión y alcance del lanzamiento | Presupuesto |

Hay una frontera que conviene no borrar: **el modelo no decide la tasa de
captura ni el percentil de corte**. Entrega el ordenamiento y la curva de
esfuerzo; cuánto se captura y a cuántos se llama son decisiones de negocio con
consecuencias de presupuesto. Presentarlas como salidas del modelo sería
atribuirle una autoridad que no tiene.

### 3.2 Flujos de información entre actores

Las flechas continuas son entregas; las punteadas, retroalimentación. Cada
etiqueta es el artefacto concreto que cambia de manos, no una relación genérica.

```mermaid
flowchart TB
    subgraph TI["TI / Plataforma"]
        TI1["Sistemas fuente<br/>7 orígenes operativos"]
    end

    subgraph AN["Analítica"]
        AN1["Pipeline medallón<br/>bronce · plata · oro"]
        AN2["Modelos A, B y monto 12m"]
        AN3["Validación y auditoría"]
        AN1 --> AN2
        AN2 --> AN3
    end

    subgraph RC["Riesgo y Cumplimiento"]
        RC1["Revisión de sesgo<br/>y de proxies"]
    end

    subgraph PD["CREAN / Producto"]
        PD1["Tasa de captura<br/>y meta de lanzamiento"]
    end

    subgraph CM["Comercial"]
        CM1["Percentil de corte<br/>y ejecución de campaña"]
    end

    subgraph DI["Dirección"]
        DI1["Decisión de inversión"]
    end

    TI1 -->|"extractos mensuales"| AN1
    AN3 -->|"informe de sesgo"| RC1
    RC1 -->|"visto bueno o hallazgo"| CM1
    AN2 -->|"dimensionamiento"| PD1
    AN2 -->|"lista priorizada<br/>niveles A/B/C/D"| CM1
    PD1 -->|"meta y supuesto"| DI1
    PD1 -->|"cupo de campaña"| CM1
    CM1 -.->|"resultado real de contacto"| AN2
    DI1 -.->|"presupuesto"| PD1

    style AN fill:#E8F1F5,stroke:#1F6F8B
    style RC fill:#FBF3DC,stroke:#D9A441
    style PD fill:#E6F2EC,stroke:#2E8B57
    style CM fill:#E6F2EC,stroke:#2E8B57
```

El lazo punteado de Comercial hacia los modelos es el que cierra el sistema: sin
el resultado real del contacto, la solución nunca aprende de sí misma y se queda
prediciendo un proxy indefinidamente. Hoy ese lazo **no está conectado** — es
trabajo de integración con el CRM, y está en la hoja de ruta del
[esquema de operación](esquema_operacion.md).

### 3.3 El proceso de punta a punta

Los rombos son **puntos de decisión** con criterio explícito y consecuencia
definida. No son revisiones informales: cada uno tiene un umbral en
`config.py` y una prueba automática que lo verifica.

```mermaid
flowchart TD
    A(["Fuentes operativas<br/><i>Actor: TI / Plataforma</i>"]) --> B["Ingesta y diagnóstico de calidad<br/><i>Actor: Analítica</i>"]
    B --> C["Integración y construcción de variables"]

    C --> D{"¿La variable supera<br/>IV, FDR y VIF?"}
    D -->|No| D1["Se descarta<br/>y queda registrada"]
    D -->|Sí| E["Entrenamiento de modelos"]

    E --> F{"¿AUC > 0,95?"}
    F -->|Sí| F1["<b>ALTO</b><br/>Se sospecha fuga de etiqueta<br/>y se investiga antes de seguir"]
    F -->|No| G["Scoring de los 860.223 clientes"]

    F1 -.->|corrección| C

    G --> H["Estimación de monto a 12 meses<br/>solo población con inversión"]
    H --> I{"¿Cumple la regla del 80%<br/>por atributo protegido?"}

    I -->|No| I1["Se documenta el hallazgo<br/><i>Actor: Riesgo / Cumplimiento</i>"]
    I -->|Sí| J["Asignación de niveles A/B/C/D<br/>por cuartil dentro de cada población"]
    I1 --> J

    J --> K{"¿Qué tasa de captura<br/>asume el negocio?"}
    K --> L["Dimensionamiento<br/><i>Actor: CREAN / Producto</i>"]

    J --> M{"¿Hasta qué percentil<br/>se contacta?"}
    M --> N["Lista priorizada<br/><i>Actor: Comercial</i>"]

    L --> O(["Decisión de inversión<br/>y metas del lanzamiento"])
    N --> P(["Campaña de contacto"])
    P --> Q["Resultado real de contacto"]
    Q -.->|retroalimenta| E

    style F1 fill:#F8E3E0,stroke:#C1554A
    style I1 fill:#FBF3DC,stroke:#D9A441
    style O fill:#E6F2EC,stroke:#2E8B57
    style P fill:#E6F2EC,stroke:#2E8B57
```

### 3.4 Los puntos de decisión, uno por uno

| Decisión | Criterio | Si no se cumple | Dónde vive |
|---|---|---|---|
| ¿La variable entra al modelo? | IV ≥ 0,02 · significativa tras corrección Benjamini-Hochberg · VIF < 10 | Se descarta y queda el registro | `src/feature_tests.py` |
| ¿Hay fuga de etiqueta? | AUC ≤ 0,95 | **Se detiene el trabajo** y se investiga | `config.UMBRAL_AUC_FUGA` |
| ¿Hay impacto dispar? | Razón de selección ≥ 0,80 | Se documenta antes de operar la lista | `src/auditoria_sesgo.py` |
| ¿El proxy de género es aceptable? | AUC < 0,60 mínimo · 0,60–0,70 moderado · > 0,70 sustancial | Moderado: se vigila. Sustancial: se investiga mitigación | `config.UMBRAL_AUC_PROXY_*` |
| ¿Qué tasa de captura se asume? | Decisión **del negocio**, no del modelo | — | `config.TASAS_CAPTURA` |
| ¿Cuántos clientes se contactan? | Curva precisión/cobertura según costo del contacto | — | Vista *Modelos* del tablero |

Ese primer control ya se activó en la práctica: el AUC llegó a **0,9497** y la
investigación encontró una fuga real — tres variables de recencia y antigüedad
se calculaban incluyendo los dos productos que definen la etiqueta. Corregidas,
el AUC quedó en **0,8933**, que es la cifra que se reporta.

---

## 4. Aporte a los procesos de CREAN

El requerimiento pide mostrar el aporte a **uno o varios** de los siete
procesos. La solución soporta cuatro de forma directa, dos parcialmente, y
**uno no lo toca en absoluto** — decirlo es más útil que forzar el encaje.

```mermaid
flowchart LR
    S["<b>Solución analítica</b>"]

    S ==>|directo| P4["Administrar información"]
    S ==>|directo| P6["Afiliar / Desafiliar<br/>al servicio"]
    S ==>|directo| P5["Monitorear el servicio"]
    S ==>|directo| P3["Gestionar el uso<br/>del servicio"]
    S -->|parcial| P2["Gestionar ingresos<br/>y gastos"]
    S -->|parcial| P7["Administrar el servicio"]
    S -.->|no aplica| P1["Conciliar transacciones<br/>y contabilidad"]

    style P4 fill:#E6F2EC,stroke:#2E8B57
    style P6 fill:#E6F2EC,stroke:#2E8B57
    style P5 fill:#E6F2EC,stroke:#2E8B57
    style P3 fill:#E6F2EC,stroke:#2E8B57
    style P2 fill:#FBF3DC,stroke:#D9A441
    style P7 fill:#FBF3DC,stroke:#D9A441
    style P1 fill:#F0F0F0,stroke:#9E9E9E,stroke-dasharray: 4 4
```

### Aporte directo

**Administrar información** — *gestionar y garantizar el ciclo de vida de la
información derivada de los servicios.*
El pipeline medallón **es** ese ciclo de vida: ingesta trazable, transformación
documentada, diagnóstico de calidad, un grano declarado y verificado por
pruebas en cada capa, y un registro de decisiones con su evidencia. Aporta
además un activo que hoy no existe: **una vista integrada del cliente** a
partir de siete fuentes que viven separadas.

**Afiliar / Desafiliar al servicio** — *gestionar la afiliación o desafiliación
de clientes.*
Es el proceso que la solución alimenta de forma más directa, y por **los dos
lados**:
- *Afiliar*: la lista priorizada de contacto. Contactando al 10% mejor
  rankeado se alcanza al **51,2% de los adoptantes** con precisión del 36,7%,
  **5,1 veces** la tasa base.
- *Desafiliar*: **40.137 clientes** que el modelo proyecta desinvirtiendo,
  −0,76 billones COP. Es una base de retención nominada, con nombre y cédula,
  que sale del mismo modelo y que nadie estaba mirando.

**Monitorear el servicio** — *hacer seguimiento al correcto funcionamiento y
detectar opciones de mejora.*
La solución llega con sus propios controles: umbral de fuga, regla del 80%,
detección de proxy de género, error de backtest y análisis de sensibilidad de
la etiqueta. El detalle de qué se vigila y con qué frecuencia está en el
[esquema de operación](esquema_operacion.md).

**Gestionar el uso del servicio** — *habilitar el correcto funcionamiento del
uso de los servicios.*
Aquí entra la población de **activación**: 309.928 clientes que tienen
productos con el banco pero ninguno de inversión. No son adquisición —ya son
clientes— sino uso no realizado.

### Aporte parcial

**Gestionar ingresos y gastos** — el dimensionamiento es el insumo de entrada
para proyectar ingresos por comisión o por activos administrados, pero la
solución **no modela la monetización**: entrega el volumen potencial, no el
ingreso.

**Administrar el servicio** — la solución define un ANS implícito (la lista
priorizada disponible el primer día hábil de cada mes) pero no gestiona
requerimientos ni novedades.

### No aplica

**Conciliar transacciones y contabilidad** — es integridad contable posterior a
la transacción. La solución es predictiva y previa al hecho: no toca registros
financieros ni los concilia. Forzar un encaje aquí sería inventarlo.

---

## 5. Del modelo a la decisión de negocio

Cierre de la cadena: qué produce cada pieza y qué decisión habilita.

| Pregunta del negocio | Qué la responde | Cifra medida |
|---|---|---|
| ¿A quién le hablamos primero? | Nivel de prioridad por población | 215.057 clientes en nivel A |
| ¿Cuántos contactamos? | Curva precisión/cobertura | Top 10% → 51,2% de cobertura |
| ¿Cuánto podría entrar? | Entrada bruta × tasa de captura | 186 / 465 / 744 mil M COP |
| ¿Es negocio nuevo o traslado? | Descomposición por componente | ≈ mitad viene de CDT y Fiducuenta |
| ¿A quién estamos por perder? | Bloque de riesgo de retiro | 40.137 clientes, −0,76 billones |
| ¿Podemos operar la lista? | Auditoría de sesgo | Proxy de género moderado (0,625) |

**La advertencia que debe acompañar la cifra de oportunidad**: aproximadamente
la mitad del monto proyectado proviene de CDT y Fiducuenta, es decir, de saldo
que **ya está en el banco**. Presentarlo como crecimiento sería contarlo dos
veces a nivel institucional. Es migración de producto, que tiene valor —
mejora la experiencia y la retención— pero no es captación neta.
