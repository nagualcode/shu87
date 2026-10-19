# Shu87 — modelo SM58 → Neumann U 87

## Ideia central

Os dois microfones são, em boa aproximação, sistemas de **fase mínima**. Então a
correção de magnitude feita com filtros de fase mínima também corrige a resposta
a transientes: desfazer a ressonância/presença do SM58 desfaz o "borrão" dele no
tempo, e aplicar as do U 87 recria o dele. A conversão é:

```
U87(f) = SM58(f) · [1/SM58(f)] · Proximidade(r58 → r87) · Cápsula_K87(f) · LowCut · FET(f) → NL(FET) → NL(Trafo)
```

Tudo roda a 2× a taxa do host (oversampling half-band FIR, 63 taps, Kaiser β=8,
latência de 31 amostras reportada ao host).

## Fontes

| Dado | Fonte |
|---|---|
| Resposta SM58 (campo distante) | Guia do usuário Shure, `research/SM58/SM58.pdf`, digitalizada (`tools/digitize.py`) |
| Resposta U 87 Ai por padrão polar, com/sem low-cut | Neumann *Product Information U 87 Ai* (Publ. 11/00), digitalizada |
| Circuito | Esquemáticos Neumann 10241-930-000.16 (1972) e 10241-901-21.7 (1980), `research/U87/` |
| Mudança C6 220p→160p, C5 33n→47n no U 87 Ai | GroupDIY, tópico "U87 circuit, and HF roll-off curve" |
| HF boost Ai em ~10 kHz vs ~8 kHz no antigo; circuito "virtualmente idêntico" | Klaus Heyne via RecordingHacks |
| THD 0,5 % @ 117 dB SPL, 390 mV máx., 28 mV/Pa (cardioide) | Datasheet Neumann |
| Modelagem filtro-fonte → filtro-alvo, proximidade como shelf de 1ª ordem | US 8 666 090 B1 (Townsend / Universal Audio) |
| Não-linearidade após filtragem (estrutura tipo Hammerstein) | US 9 173 046 B2 (Sennheiser) |

## Blocos

### 1. Inversa do SM58 (`SM58_INVERSE`)
A curva da Shure foi ajustada com HP 2ª ordem (86 Hz), 4 picos (presença 3,7–7 kHz,
vale em 7,6 kHz, pico em 10,8 kHz) e LP 2ª ordem (10,2 kHz) — erro RMS 0,29 dB.
Os picos são invertidos exatamente (pico RBJ com ganho negado). As bordas de banda
são **regularizadas**: o grave é estendido só uma oitava (HP em 43 Hz) e o agudo
até 16,5 kHz. Abaixo/acima disso o SM58 entrega ruído de manuseio e chiado, e
inverter "até o fim" só amplificaria isso.

### 2. Proximidade
Para um microfone de gradiente de 1ª ordem a distância `r` de uma fonte pontual:
`H(s) = 1 + g·c/(s·r)`, com `g` = fração de gradiente (omni 0, cardioide 0,5, figura-8 1).
Remapear SM58 em `r58` para U 87 em `r87` é a razão `(s + a87)/(s + a58)`, um
shelf de 1ª ordem. As distâncias são medidas até a grade; o diafragma fica
~1,5 cm atrás (SM58) e ~2 cm atrás (U 87). Consequência física correta: em
**Omni** não existe efeito de proximidade, então um SM58 gravado colado soa mais
magro no modo Omni.

### 3. Cápsula K87 (`CAPSULE_*`)
`Cápsula = curva_Neumann(padrão) / FET_Ai`, ajustada com HP2 + 2 picos + LP2.
Erro RMS: cardioide 0,23 dB, omni 0,13 dB, figura-8 0,25 dB.

### 4. Estágio FET com realimentação pela cápsula (`FET_AI`, `FET_VINTAGE`)
Lendo o esquemático: o sinal do dreno volta por **C9** para o trilho de
polarização, passa por **R8 (1 MΩ) ‖ C6** até o nó do backplate, que vai ao terra
por **C5 + R9 (6,8 k) + R10 (560 Ω)**. A cápsula (2×50 pF) contra C1 (470 pF) +
C3 acopla uma fração `k` dessa tensão de volta ao gate — **a própria cápsula fica
dentro da malha de realimentação negativa**:

```
β(s) = Zbot / (Ztop + Zbot)     Ztop = R8 ‖ 1/(sC6)    Zbot = R9 + R10 + 1/(sC5)
G(s) = A / (1 + A·k·β(s))
```

Isso é um biquad analítico. C6 controla quanto agudo é realimentado (mais C6 →
menos agudo); C5 controla o corte fixo de graves (mais C5 → mais grave). Por isso
a troca para 160 pF / 47 nF no Ai dá "um pouco mais de agudo e de grave", como
relatado. **Estimativa:** o produto ganho-de-malha `A·k = 3,4` não está no
esquemático (depende do gm do FET e da relação do trafo); foi escolhido para
gm ≈ 3 mS, carga efetiva ≈ 12 kΩ, k ≈ 0,093. Ele só afeta a *diferença* entre
as versões — a curva Ai total é forçada a bater com a publicada.

| | 20 Hz | 50 Hz | 10 kHz | 20 kHz |
|---|---|---|---|---|
| FET Ai | −1,65 | −0,31 | −0,37 | −1,32 dB |
| FET vintage | −2,76 | −0,60 | −0,66 | −2,16 dB |

### 5. Low cut
Ajustado na diferença entre as curvas cardioide com e sem filtro: 1ª ordem em
389 Hz (erro máx. 0,7 dB entre 50 Hz e 1 kHz). A Neumann diz que o filtro atua
na entrada do amplificador, então ele vem antes do FET.

### 6. Não-linearidades (calibradas no datasheet)
Amplitude interna 1,0 = 117 dB SPL = 0,5 % THD (Drive 0 dB → 0 dBFS).
- **FET** (lei quadrática do JFET): `y = x + 0,008·x²` → 0,4 % de 2º harmônico no
  máximo; acima disso, compressão suave (fim da excursão do dreno).
- **Transformador**: corrente de magnetização cúbica no fluxo (`φ = ∫v`), que cai
  sobre a impedância da fonte: `y = x − 0,04·φ³`. Como `φ ∝ V/f`, o 3º harmônico
  cresce ~1/f³: 1 % em 30 Hz no máximo, praticamente zero acima de 200 Hz.
  Histerese não é modelada.

Em níveis normais de voz (−18 a −12 dBFS) a distorção é < 0,1 %, como no
microfone real. O U 87 não é um microfone "de saturação"; o caráter dele é
quase todo linear. Use **Drive** para empurrar mais.

## Verificação (`cargo test --release`)
- Curva SM58 publicada → plugin → bate com a curva U 87 Ai publicada em
  < 2 dB de 150 Hz a 12 kHz nos três padrões polares.
- Vintage vs Ai: menos ar e menos grave, nas magnitudes esperadas.
- SM58 a 2 cm → U 87 a 30 cm remove 8–20 dB de grave de proximidade.
- Troca de padrão/versão/low-cut/distâncias com seno de 1 kHz: sem degraus
  (crossfade de 30 ms; nenhuma troca abrupta de coeficientes).
- `process()` sem alocação (rt-paranoid); `auval` passa.

## Limites honestos
- Só a resposta **no eixo** é transformada. O padrão polar do SM58 já decidiu
  quanto de sala entrou na gravação; Omni/Figura-8 mudam o timbre e a
  proximidade, não recriam a captação da sala.
- Acima de ~16 kHz o SM58 não captou quase nada; nenhum EQ recria isso.
- Cada SM58 varia ±2–3 dB em relação à curva típica da Shure. Para chegar mais
  perto, a melhoria seguinte seria medir o *seu* SM58 (varredura com um
  microfone de medição de referência) e trocar `research/data/sm58.csv`;
  `tools/model.py` regenera tudo.

## Regenerar
```
python3 -I tools/digitize.py   # curvas -> research/data/*.csv
python3 -I tools/model.py      # ajuste -> src/coeffs.rs + docs/model_fit.png
cargo test --release
cargo truce install --au2
```
