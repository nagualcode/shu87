# Pacote "U87 Condenser Mic IR's" (Past to Future) — análise

Arquivos: `research/impulse_response/U87 {05,1,2,4,5}inch{,_441}.wav`.
Segundo o fabricante: U 87 antigo (não Ai), 96 e 44,1 kHz. Nada é dito sobre o
microfone de referência nem sobre o método de captura.

## Achados

1. **Mono, banda limitada.** L = R. Mesmo os arquivos de 96 kHz caem −28 dB em
   25 kHz: a captura foi feita a 44,1/48 kHz e reamostrada.
2. **Não é o U 87 sozinho.** As IRs têm um vale de −3 a −5 dB em 2–5 kHz e um
   realce de 8 a 12 kHz, onde o U 87 é plano. A "referência implícita"
   (U 87 vintage modelado − IR) tem +2 a +3,5 dB de presença em 2–7 kHz, mas não
   o pico de 10 kHz do SM58. É compatível com U 87 ÷ (dinâmico tipo SM57 ou
   alto-falante), mas a referência **não é identificável** a partir dos dados.
3. **São só duas capturas, não cinco.** As IRs de 1″, 2″, 4″ e 5″ têm detalhe
   agudo idêntico (correlação 0,999): é uma captura com EQ de grave diferente
   por "distância". Portanto as diferenças de grave entre elas também são
   sintéticas, não medidas. A de 0,5″ é outra captura.
4. **O detalhe fino não se repete entre as duas capturas.** Em 3–15 kHz cada
   uma tem ~0,73 dB RMS de microestrutura, mas a correlação entre elas é +0,05 e
   os sinais concordam em 55 % das frequências (acaso = 50 %).

## Conclusão

As microrressonâncias desse pacote são a assinatura de cada sessão de medição
(posição, referência, alto-falante, sala), não uma propriedade reproduzível do
U 87. Aplicá-las no Shu87 como "detalhe do U 87" seria copiar um artefato de
medição. O mesmo raciocínio se aplica à IR do BESURE, de procedência ainda
menos conhecida. Por isso nada deste pacote alimenta o plugin.

Para capturar microrressonâncias que sejam de fato do microfone, a medição
precisa de: referência conhecida (microfone de medição omni), várias posições
**independentes**, janela temporal curta (sem sala) e, de preferência, o seu
próprio SM58 medido na mesma sessão. Só o que se repetir entre posições entra
no modelo.

Reproduzir: `python3 -I tools/detail.py` (gera `docs/detail.png`).
