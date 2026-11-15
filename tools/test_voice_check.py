"""Short-line listening check (issues 2/3 from Emmanuel's video: "One apples", "Two is... one, two hey"):
the re-take plan for a garbled short line. Fast, no models:  python3 tools/test_voice_check.py
(The listening itself runs inside tools/gen_voice.py for every line of <= voice.verifyShort words.)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice_check as V
fails = []
def ok(c, m):
    print(('ok    ' if c else 'FAIL  ') + m)
    c or fails.append(m)
t = V.takes('Six!', 0.95)
ok(t[0] == ('Six!', 0.95), 'first take is the line as written')
ok(('Six.', 0.95) in t, "calm full stop instead of '!'")
ok(('Six', 0.95) in t, 'no end mark (one-word lines grow a vowel tail with one: "Zexa")')
ok(any(abs(s - 1.03) < 1e-9 for _, s in t) and any(abs(s - 0.9) < 1e-9 for _, s in t), 'a touch faster and a touch slower')
ok(len(t) == len(set(t)), 'no take repeated')
t2 = V.takes('One apple', 1.0)
ok(len(t2) == len(set(t2)) and t2[0] == ('One apple', 1.0), 'line without end mark: no duplicate takes')
print('VOICE CHECK TESTS ' + ('FAILED ' + str(fails) if fails else 'PASSED'))
sys.exit(1 if fails else 0)
