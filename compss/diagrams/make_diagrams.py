"""Draw the diagrams in compss/README.md. Needs matplotlib.

	python3 compss/diagrams/make_diagrams.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parent

# fill, edge, text
COLORS = {
	"slurm": ("#ECEFF3", "#5B6573", "#2E3742"),
	"compss": ("#E3EEFB", "#2F6DB5", "#1B4A80"),
	"app": ("#E4F4E6", "#2E8B47", "#1C5E2F"),
	"qfw": ("#FDEFE1", "#D07A1F", "#8A4B0C"),
}
INK = "#26303A"
MUTED = "#5E6873"
ORANGE = "#8A4B0C"


def canvas(width, height, title):
	fig, ax = plt.subplots(figsize=(width / 8, height / 8))
	ax.set_xlim(0, width)
	ax.set_ylim(0, height)
	ax.axis("off")
	ax.text(width / 2, height - 1, title, ha="center", va="top", fontsize=18,
			fontweight="bold", color=INK)
	return fig, ax


def box(ax, x, y, w, h, title, subtitle=None, kind="slurm", top=False):
	"""A rounded box. With top=True the title sits at the top, as a container."""
	fill, edge, text = COLORS[kind]
	ax.add_patch(FancyBboxPatch(
		(x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
		fc=fill, ec=edge, lw=1.6, zorder=2))
	if top:
		title_y = y + h - 2.2
	else:
		title_y = y + h / 2 + (1.1 if subtitle else 0)
	ax.text(x + w / 2, title_y, title, ha="center", va="center", fontsize=11.5,
			fontweight="bold", color=text, zorder=3)
	if subtitle:
		ax.text(x + w / 2, title_y - 2.3, subtitle, ha="center", va="center",
				fontsize=10, color=INK, zorder=3)


def arrow(ax, start, end, label=None, color=INK, dashed=False, both=False,
		  label_x=None, label_y=None):
	ax.add_patch(FancyArrowPatch(
		start, end, arrowstyle="<|-|>" if both else "-|>", mutation_scale=13,
		color=color, lw=1.6, ls=(0, (4, 3)) if dashed else "-", zorder=4,
		shrinkA=0, shrinkB=0))
	if label:
		x = label_x if label_x is not None else (start[0] + end[0]) / 2
		y = label_y if label_y is not None else (start[1] + end[1]) / 2
		ax.text(x, y, label, ha="center", va="center", fontsize=10, color=color,
				zorder=5, bbox=dict(fc="white", ec="none", pad=1.5))


def architecture():
	fig, ax = canvas(100, 83, "COMPSs and QFw on the cluster")

	box(ax, 15, 70, 70, 7, "Slurm job",
		"nodes c1, c2, c3 and a reservation on the quantum simulator")
	box(ax, 15, 56, 70, 8, "c1: COMPSs master and your main program",
		"started by qfw-compss-launch; creates the tasks and waits for results",
		"compss")
	arrow(ax, (50, 70), (50, 64))

	for x, name in ((4, "c2"), (54, "c3")):
		box(ax, x, 23, 42, 27, f"{name}: COMPSs worker, up to 4 tasks at a time",
			kind="compss", top=True)
		box(ax, x + 3, 37.5, 36, 7, "@task function", "uses a QFwClient", "app")
		box(ax, x + 3, 25, 36, 7, "defw-python child",
			"one per client, stays open", "qfw")
		arrow(ax, (x + 21, 37.5), (x + 21, 32), "pipes", both=True)
		arrow(ax, (x + 21, 56), (x + 21, 50))

	box(ax, 4, 5, 28, 9, "slurmctld", "DEFw directory, gateway", "qfw")
	box(ax, 36, 5, 60, 9, "nwqsim-head", "QPM and NWQ-Sim, shared by all tasks",
		"qfw")
	arrow(ax, (15, 25), (15, 14), "find the QPM", ORANGE)
	arrow(ax, (40, 25), (40, 14), "circuits, results", ORANGE, both=True)
	arrow(ax, (75, 25), (75, 14), "circuits, results", ORANGE, both=True)

	fig.savefig(OUT / "architecture.png", dpi=150, bbox_inches="tight",
				facecolor="white")
	plt.close(fig)


def quantum_task():
	fig, ax = canvas(100, 72, "One quantum task")

	lanes = (
		(13, "COMPSs master", "c1", "compss"),
		(38, "@task, QFwClient", "c2 or c3", "app"),
		(63, "defw-python child", "same node", "qfw"),
		(88, "QPM", "nwqsim-head", "qfw"),
	)
	bottom = 3
	for x, name, where, kind in lanes:
		ax.plot([x, x], [bottom, 61], color=COLORS[kind][1], lw=1.2,
				ls=(0, (4, 3)), zorder=1)
		box(ax, x - 11, 61, 22, 6, name, where, kind)
	master, task, child, qpm = (lane[0] for lane in lanes)

	def message(start, end, y, label, dashed=False, color=INK):
		arrow(ax, (start, y), (end, y), color=color, dashed=dashed)
		ax.text((start + end) / 2, y + 0.4, label, ha="center", va="bottom",
				fontsize=10, color=color, zorder=5,
				bbox=dict(fc="white", ec="none", pad=0.8))

	message(master, task, 56, "start the task")
	message(task, child, 50, "open the client: start the child")
	message(child, qpm, 44, "find the QPM, connect", color=ORANGE)
	ax.text((child + qpm) / 2, 42.3, "about 7.5 s, once per client", ha="center",
			va="center", fontsize=10, color=MUTED, zorder=5,
			bbox=dict(fc="white", ec="none", pad=1.5))

	# The calls that repeat for as long as the client is open.
	ax.add_patch(Rectangle((31, 18), 67, 19, fc="#F7F8FA", ec=MUTED, lw=1,
						   ls=(0, (5, 3)), zorder=0))
	ax.text(task + 1, 36, "repeats for each call", ha="left", va="top",
			fontsize=10, color=MUTED, fontweight="bold")
	message(task, child, 31, "estimator or sampler call")
	message(child, qpm, 27.5, "circuits", color=ORANGE)
	message(qpm, child, 24, "results", dashed=True, color=ORANGE)
	message(child, task, 20.5, "results", dashed=True)

	message(task, child, 13, "close the client: the child exits")
	message(task, master, 7, "return the task's result", dashed=True)

	fig.savefig(OUT / "quantum-task.png", dpi=150, bbox_inches="tight",
				facecolor="white")
	plt.close(fig)


if __name__ == "__main__":
	architecture()
	quantum_task()
