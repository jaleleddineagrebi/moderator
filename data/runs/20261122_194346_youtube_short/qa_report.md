# QA report: CHANGES NEEDED

- ✅ **length** [en]: 45.3s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 45.3s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.2 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.3s (target <= 4s)
- ✅ **caption sync** [en]: 108 words, 40 caption events
- ✅ **visual licenses**: 8 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: The math trick in scene 3 is incorrect. If the viewer adds 8 and then divides by 2, they have (x+8)/2 = x/2 + 4. Subtracting the original number (x) results in -x/2 + 4, not 4. To make the result always 4, the instruction in scene 3 must be 'Subtract half your original number' or the instruction in scene 2 must be changed to 'Add eight to your result' after multiplying by 2, then divide the whole thing by 2 and subtract the original number. The simplest fix for the script: in scene 2 say 'Double it. Now add eight.' and in scene 3 say 'Divide the total by two. Subtract your original number. You’re left with four.' (This works: ((2x+8)/2)-x = 4). However, the current script implies 'Add eight' to the original number or the product. If the user follows: ((x*2)+8)/2 - x, the answer is 4. The script is technically correct but the phrasing 'add eight' after 'multiply it by two' needs to be clearly part of the sequence. The bigger issue is scene 8's VO ends abruptly with 'which is exactly why...' without finishing the thought. Fix: Remove 'which is exactly why...' from the end of scene 8. → sent to script
- ✅ **people rule**: no women beyond face close-ups in 8 scenes and 1 thumbnail(s)