# QA report: CHANGES NEEDED

- ✅ **length** [en]: 45.1s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 45.1s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.2 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.5s (target <= 4s)
- ✅ **caption sync** [en]: 101 words, 41 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: The mathematical trick in scene 02 and 03 is incorrectly solved in the script. Following the steps: (x * 2 + 8) / 2 - x = (2x + 8) / 2 - x = x + 4 - x = 4. However, if the user picks 0, it works, but if they pick a number and the voiceover says 'You are left with four', and then the on-screen text in scene 05 says 'CHOOSE A COLOR' while the narration asks to visualize furniture, it is inconsistent. More importantly, the math result is 4, but the text 'YOUR NUMBER IS 4' is correct. The actual error is the claim of 'semantic priming' for a 'Red Chair' in scene 06 when no priming for 'red' or 'chair' occurred in the previous scenes. However, looking strictly at the math: (x*2+8)/2-x always equals 4. The math is correct. → sent to script
- ⚠️ **visual_fit review** [en]: In scene 05, the on-screen text says 'CHOOSE A COLOR' but the narration asks to visualize a 'piece of furniture' first and then a color. Change on-screen text to 'FURNITURE + COLOR' to match the dual instruction.
- ✅ **people rule**: no women beyond face close-ups in 7 scenes and 1 thumbnail(s)