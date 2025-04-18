from re import findall 
from math import floor
from time import time
from os import path as ospath, stat
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
from shlex import split as ssplit
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE

from bot import Var, bot_loop, ffpids_cache, LOGS
from .func_utils import mediainfo, convertBytes, convertTime, sendMessage, editMessage
from .reporter import rep

ffargs = {
    '1080': Var.FFCODE_1080,
    '720': Var.FFCODE_720,
    '480': Var.FFCODE_480,
    '360': Var.FFCODE_360,
    }

class FFEncoder:
    def __init__(self, message, path, name, qual):
        self.__proc = None
        self.is_cancelled = False
        self.message = message
        self.__name = name
        self.__qual = qual
        self.dl_path = path
        self.__total_time = None
        self.out_path = ospath.join("encode", name)
        self.__prog_file = 'prog.txt'
        self.__start_time = time()

    async def validate_output(self, path):
        try:
            return ospath.exists(path) and stat(path).st_size > 0
        except OSError:
            return False

    async def progress(self):
        self.__total_time = await mediainfo(self.dl_path, get_duration=True)
        if isinstance(self.__total_time, str):
            self.__total_time = 1.0
        while not (self.__proc is None or self.is_cancelled):
            async with aiopen(self.__prog_file, 'r+') as p:
                text = await p.read()
            if text:
                time_done = floor(int(t[-1]) / 1000000) if (t := findall("out_time_ms=(\d+)", text)) else 1
                ensize = int(s[-1]) if (s := findall(r"total_size=(\d+)", text)) else 0
                
                diff = time() - self.__start_time
                speed = ensize / diff
                percent = round((time_done/self.__total_time)*100, 2)
                tsize = ensize / (max(percent, 0.01)/100)
                eta = (tsize-ensize)/max(speed, 0.01)
    
                bar = floor(percent/8)*"█" + (12 - floor(percent/8))*"▒"
                
                progress_str = f"""<blockquote>‣ <b>𝙰𝚗𝚒𝚖𝚎 𝙽𝚊𝚖𝚎 :</b> <b>{self.__name}</b></blockquote>
<blockquote>‣ <b>𝚂𝚝𝚊𝚝𝚞𝚜 :</b>𝙴𝚗𝚌𝚘𝚍𝚒𝚗𝚐 𝙴𝚙𝚒𝚜𝚘𝚍𝚎
    <code>[{bar}]</code> {percent}%</blockquote> 
<blockquote>   ‣ <b>𝚂𝚒𝚣𝚎 :</b> {convertBytes(ensize)} out of ~ {convertBytes(tsize)}
    ‣ <b>𝚂𝚙𝚎𝚎𝚍 :</b> {convertBytes(speed)}/s
    ‣ <b>𝚃𝚒𝚖𝚎 𝚃𝚘𝚘𝚔 :</b> {convertTime(diff)}
    ‣ <b>𝚃𝚒𝚖𝚎 𝙻𝚎𝚏𝚝 :</b> {convertTime(eta)}</blockquote>
<blockquote>‣ <b>𝙵𝚒𝚕𝚎(𝚜) 𝙴𝚗𝚌𝚘𝚍𝚎𝚍:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""
            
                await editMessage(self.message, progress_str)
                if (prog := findall(r"progress=(\w+)", text)) and prog[-1] == 'end':
                    break
            await asleep(8)
    
    async def start_encode(self):
        if ospath.exists(self.__prog_file):
            await aioremove(self.__prog_file)
    
        async with aiopen(self.__prog_file, 'w+'):
            LOGS.info("Progress Temp Generated !")
            pass
        
        dl_npath, out_npath = ospath.join("encode", "ffanimeadvin.mkv"), ospath.join("encode", "ffanimeadvout.mkv")
        await aiorename(self.dl_path, dl_npath)
        
        ffcode = ffargs[self.__qual].format(dl_npath, self.__prog_file, out_npath)
        
        LOGS.info(f'FFCode: {ffcode}')
        self.__proc = await create_subprocess_shell(ffcode, stdout=PIPE, stderr=PIPE)
        proc_pid = self.__proc.pid
        ffpids_cache.append(proc_pid)
        _, return_code = await gather(create_task(self.progress()), self.__proc.wait())
        ffpids_cache.remove(proc_pid)
        
        await aiorename(dl_npath, self.dl_path)
        
        if self.is_cancelled:
            return None

        if return_code == 0:
            if await self.validate_output(out_npath):
                await aiorename(out_npath, self.out_path)
                return self.out_path
            else:
                await rep.report("Encoding produced empty/invalid file", "error")
                return None
        else:
            error_msg = (await self.__proc.stderr.read()).decode().strip()
            await rep.report(f"Encoding failed: {error_msg}", "error")
            return None
            
    async def cancel_encode(self):
        self.is_cancelled = True
        if self.__proc is not None:
            try:
                self.__proc.kill()
            except:
                pass
