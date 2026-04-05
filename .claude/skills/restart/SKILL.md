---
name: restart
description: Restart the Media Luna Flask server and confirm it came back up
---

Run the following command to restart the Media Luna Flask server and confirm it came back up:

```bash
sudo systemctl restart media-luna.service && sudo systemctl status media-luna.service --no-pager -l
```
