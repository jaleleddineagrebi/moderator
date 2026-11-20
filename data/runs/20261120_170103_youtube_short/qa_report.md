# QA report: CHANGES NEEDED

- ✅ **length** [en]: 45.2s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 45.2s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.2 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.9s (target <= 4s)
- ✅ **caption sync** [en]: 93 words, 37 caption events
- ✅ **visual licenses**: 8 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: In scene_06, the claim that the real answer is 4100 is incorrect. 1000 + 40 + 1000 + 30 + 1000 + 20 + 1000 + 10 equals 4100, but the video script claims people say 5000 incorrectly because of a glitch. The math provided in the script actually adds up to 4100, so saying 4100 is the correct answer and 5000 is wrong is correct, but the prompt implies a trick. However, the sequence 4090 + 10 is where the 'glitch' usually happens making people say 5000. The script as written is factually consistent with the math, but the ending of scene_08 'which is exactly why you must' is a sentence fragment that cuts off. Change scene_08 narration to '...which is exactly why you should' to end more naturally or ensure the loop is seamless. → sent to script
- ✅ **people rule**: no women beyond face close-ups in 8 scenes and 1 thumbnail(s)