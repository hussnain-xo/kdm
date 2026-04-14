# KDM Start Instructions

## GUI Window Open Karne Ke Liye:

### Step 1: Terminal Mein Correct Directory Par Jao
```bash
cd ~/kdm
```

### Step 2: KDM Start Karo
```bash
python3 kdm.py
```

**Ya ek hi command mein:**
```bash
cd ~/kdm && python3 kdm.py
```

## Alternative: Start Script Use Karo
```bash
cd ~/kdm
./start_kdm.sh
```

## Important Notes:
- ✅ File location: `/Users/hussnainasif/kdm/kdm.py`
- ✅ Pehle `cd ~/kdm` karo, phir `python3 kdm.py` run karo
- ✅ GUI window automatically khulegi
- ✅ Server `http://127.0.0.1:9669` par start hoga

## Agar Error Aaye:
- Check karo: `ls ~/kdm/kdm.py` (file exist karti hai ya nahi)
- Python check karo: `python3 --version`
- Dependencies check karo: `pip3 list | grep -i "pyqt\|yt-dlp\|playwright"`
