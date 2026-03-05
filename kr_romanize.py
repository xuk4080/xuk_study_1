"""
韩语 → 국어 로마자 표기법 RR（Revised Romanization, 2000）
无需第三方库，纯 Unicode 计算。
"""

# ── 초성 (19개) ───────────────────────────────────────────────────────────────
CHO_LIST = [
    'ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ',
    'ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'
]

CHO_RR = {
    'ㄱ':'g', 'ㄲ':'kk','ㄴ':'n', 'ㄷ':'d', 'ㄸ':'tt',
    'ㄹ':'r', 'ㅁ':'m', 'ㅂ':'b', 'ㅃ':'pp','ㅅ':'s',
    'ㅆ':'ss','ㅇ':'',  'ㅈ':'j', 'ㅉ':'jj','ㅊ':'ch',
    'ㅋ':'k', 'ㅌ':'t', 'ㅍ':'p', 'ㅎ':'h',
}

# ── 중성 (21개) ───────────────────────────────────────────────────────────────
JUNG_RR = [
    'a','ae','ya','yae','eo','e','yeo','ye','o',
    'wa','wae','oe','yo','u','wo','we','wi','yu',
    'eu','ui','i'
]

# ── 종성 (28개, index 0~27, 0=없음) ─────────────────────────────────────────
# Unicode 표준 순서 (절대 바꾸지 말것)
JONG_LIST = [
    None,  # 0: 없음
    'ㄱ',  # 1
    'ㄲ',  # 2
    'ㄳ',  # 3  (ㄱ+ㅅ)
    'ㄴ',  # 4
    'ㄵ',  # 5  (ㄴ+ㅈ)
    'ㄶ',  # 6  (ㄴ+ㅎ)
    'ㄷ',  # 7
    'ㄹ',  # 8
    'ㄺ',  # 9  (ㄹ+ㄱ)
    'ㄻ',  # 10 (ㄹ+ㅁ)
    'ㄼ',  # 11 (ㄹ+ㅂ)
    'ㄽ',  # 12 (ㄹ+ㅅ)
    'ㄾ',  # 13 (ㄹ+ㅌ)
    'ㄿ',  # 14 (ㄹ+ㅍ)
    'ㅀ',  # 15 (ㄹ+ㅎ) ← 이전에 빠진 부분
    'ㅁ',  # 16
    'ㅂ',  # 17
    'ㅄ',  # 18 (ㅂ+ㅅ)
    'ㅅ',  # 19
    'ㅆ',  # 20
    'ㅇ',  # 21
    'ㅈ',  # 22
    'ㅊ',  # 23
    'ㅋ',  # 24
    'ㅌ',  # 25
    'ㅍ',  # 26
    'ㅎ',  # 27
]

# 종성 단독/자음 앞 표기
JONG_ALONE = {
    None: '',
    'ㄱ':'k',  'ㄲ':'k',  'ㄳ':'k',
    'ㄴ':'n',  'ㄵ':'n',  'ㄶ':'n',
    'ㄷ':'t',
    'ㄹ':'l',  'ㄺ':'k',  'ㄻ':'m',  'ㄼ':'p',
               'ㄽ':'l',  'ㄾ':'l',  'ㄿ':'p',  'ㅀ':'l',
    'ㅁ':'m',
    'ㅂ':'p',  'ㅄ':'p',
    'ㅅ':'t',  'ㅆ':'t',
    'ㅇ':'ng',
    'ㅈ':'t',  'ㅊ':'t',
    'ㅋ':'k',  'ㅌ':'t',  'ㅍ':'p',  'ㅎ':'t',
}

# 연음: 종성 + ㅇ 초성 → 종성이 다음 초성으로 이동
JONG_LINK = {
    None: '',
    'ㄱ':'g',  'ㄲ':'kk', 'ㄳ':'s',
    'ㄴ':'n',  'ㄵ':'j',  'ㄶ':'n',
    'ㄷ':'d',
    'ㄹ':'r',  'ㄺ':'g',  'ㄻ':'m',  'ㄼ':'b',
               'ㄽ':'r',  'ㄾ':'r',  'ㄿ':'p',  'ㅀ':'r',
    'ㅁ':'m',
    'ㅂ':'b',  'ㅄ':'s',
    'ㅅ':'s',  'ㅆ':'ss',
    'ㅇ':'ng',
    'ㅈ':'j',  'ㅊ':'ch',
    'ㅋ':'k',  'ㅌ':'t',  'ㅍ':'p',  'ㅎ':'h',
}

# ── 音변화 규칙 ────────────────────────────────────────────────────────────────
# (종성자음, 다음_초성자음) -> (종성_출력, 초성_출력)

SOUND_CHANGE: dict[tuple, tuple] = {}

# 1. 비음화
_nasalize_jong = {
    'ㄱ':'ng','ㄲ':'ng','ㄳ':'ng','ㄺ':'ng',
    'ㄷ':'n', 'ㅅ':'n', 'ㅆ':'n', 'ㅈ':'n', 'ㅊ':'n', 'ㅌ':'n',
    'ㅂ':'m', 'ㅄ':'m', 'ㄼ':'m', 'ㄿ':'m',
}
for j, jo in _nasalize_jong.items():
    SOUND_CHANGE[(j, 'ㄴ')] = (jo, 'n')
    SOUND_CHANGE[(j, 'ㅁ')] = (jo, 'm')

# 2. 유음화
SOUND_CHANGE[('ㄴ', 'ㄹ')] = ('l', 'l')
SOUND_CHANGE[('ㄹ', 'ㄴ')] = ('l', 'l')
SOUND_CHANGE[('ㄹ', 'ㄹ')] = ('l', 'l')

# 3. 격음화 (ㅎ 탈락 + 격음)
SOUND_CHANGE[('ㅎ', 'ㄱ')] = ('', 'k')
SOUND_CHANGE[('ㅎ', 'ㄷ')] = ('', 't')
SOUND_CHANGE[('ㅎ', 'ㅈ')] = ('', 'ch')
SOUND_CHANGE[('ㅎ', 'ㅂ')] = ('', 'p')
SOUND_CHANGE[('ㄱ', 'ㅎ')] = ('', 'k')
SOUND_CHANGE[('ㄷ', 'ㅎ')] = ('', 't')
SOUND_CHANGE[('ㅂ', 'ㅎ')] = ('', 'p')
SOUND_CHANGE[('ㅈ', 'ㅎ')] = ('', 'ch')
SOUND_CHANGE[('ㅀ', 'ㄴ')] = ('l', 'l')   # ㄹㅎ + ㄴ

# 4. ㄱ 종성 + ㄹ 초성 → ng + n (독립: ㄱ+ㄹ 비음화+유음화)
SOUND_CHANGE[('ㄱ', 'ㄹ')] = ('ng', 'n')
SOUND_CHANGE[('ㄲ', 'ㄹ')] = ('ng', 'n')


def _split_syllable(cp: int):
    cp -= 0xAC00
    jong_i = cp % 28
    cp //= 28
    jung_i = cp % 21
    cho_i  = cp // 21
    return cho_i, jung_i, jong_i


def korean_to_roman(text: str) -> str:
    """将含韩文的字符串转为 RR 罗马字，非韩文字符原样保留。"""
    # 第1步：分解音节
    parsed = []
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3:
            ci, ji, ki = _split_syllable(cp)
            cho_j  = CHO_LIST[ci]
            jong_j = JONG_LIST[ki]
            parsed.append({
                't':     'kor',
                'cho':   cho_j,
                'cho_r': CHO_RR[cho_j],
                'jung':  JUNG_RR[ji],
                'jong':  jong_j,
            })
        else:
            parsed.append({'t': 'raw', 'ch': ch})

    # 第2步：音변화 처리
    n = len(parsed)
    for i in range(n):
        s = parsed[i]
        if s['t'] != 'kor' or s['jong'] is None:
            continue

        # 다음 한글 음절 찾기
        ni = i + 1
        while ni < n and parsed[ni]['t'] == 'raw':
            ni += 1
        if ni >= n or parsed[ni]['t'] != 'kor':
            continue

        nxt  = parsed[ni]
        jong = s['jong']
        ncho = nxt['cho']

        if ncho == 'ㅇ':
            # 연음: 종성이 다음 초성으로 이동
            s['jong_r']    = ''
            nxt['cho_r']   = JONG_LINK.get(jong, '')
        elif (jong, ncho) in SOUND_CHANGE:
            jout, cout = SOUND_CHANGE[(jong, ncho)]
            s['jong_r']  = jout
            nxt['cho_r'] = cout

    # 第3步：조립
    result = []
    for s in parsed:
        if s['t'] == 'raw':
            result.append(s['ch'])
        else:
            ini = s['cho_r']
            vow = s['jung']
            if 'jong_r' in s:
                fin = s['jong_r']
            elif s['jong'] is None:
                fin = ''
            else:
                fin = JONG_ALONE.get(s['jong'], '')
            result.append(ini + vow + fin)

    return ''.join(result)


if __name__ == "__main__":
    tests = [
        ("가족",    "gajok"),
        ("사랑",    "sarang"),
        ("학교",    "hakgyo"),
        ("먹다",    "meokda"),
        ("서울",    "seoul"),
        ("한국어",  "hangugeo"),
        ("대학교",  "daehakgyo"),
        ("음악",    "eumak"),
        ("국어",    "gugeo"),
        ("독립",    "dongnip"),
        ("신라",    "silla"),
        ("낙동강",  "nakdonggang"),
        ("독도",    "dokdo"),
        ("불국사",  "bulguksa"),
        ("설악산",  "seoraksan"),
        ("한국",    "hanguk"),
        ("인천",    "incheon"),
        ("부산",    "busan"),
        ("김치",    "gimchi"),
        ("태권도",  "taegwondo"),
        ("공부",    "gongbu"),
        ("연습",    "yeonseup"),
        ("행복",    "haengbok"),
    ]
    print("韩语 RR 罗马字化测试")
    print("-" * 52)
    ok_cnt = 0
    for word, expected in tests:
        got  = korean_to_roman(word)
        ok   = got == expected
        ok_cnt += ok
        mark = "✅" if ok else "⚠️ "
        print(f"  {mark} {word:8s} → {got:18s}  期望: {expected}")
    print(f"\n通过 {ok_cnt}/{len(tests)}")
