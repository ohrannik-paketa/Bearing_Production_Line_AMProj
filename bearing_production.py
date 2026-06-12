"""
bearing_production.py
==========================
Parallel simulation of a ball bearing production line.
Includes assembly part-loss and packaging faults.
"""
import sys
import msvcrt
import random
import time
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Deque, List, Optional, Tuple

class Quality(Enum):
    OK = auto()
    DEFECTIVE = auto()

@dataclass
class Component:
    name: str
    serial: int
    quality: Quality = Quality.OK
    defect_reason: Optional[str] = None

@dataclass
class BallBearing:
    serial: int
    outer_ring: Optional[Component] = None
    inner_ring: Optional[Component] = None
    steel_balls: Optional[Component] = None
    cage: Optional[Component] = None
    quality: Quality = Quality.OK
    defect_reason: Optional[str] = None
    packaged: bool = False

    def is_complete(self) -> bool:
        return all([self.outer_ring, self.inner_ring, self.steel_balls, self.cage])

class Station(ABC):
    def __init__(self, name: str, defect_rate: float = 0.0):
        self.name = name
        self.defect_rate = defect_rate
        self.processed = 0
        self.rejected = 0
        self.run_flag = None
        self.stop_event = None

    def _sleep(self, duration: float):
        """Interruptible sleep allowing for E-Stop freezes and Soft Halts."""
        elapsed = 0.0
        while elapsed < duration:
            if self.run_flag: self.run_flag.wait()
            if self.stop_event and self.stop_event.is_set(): break
            time.sleep(0.05)
            elapsed += 0.05

    @abstractmethod
    def process(self, item):
        ...

    def _maybe_defect(self, reasons: List[str]) -> Tuple[Quality, Optional[str]]:
        if random.random() < self.defect_rate:
            return Quality.DEFECTIVE, random.choice(reasons)
        return Quality.OK, None

    def log(self, message: str) -> None:
        print(f"[{self.name:<20}] {message}")

class ComponentMaker(Station):
    def __init__(self, component_name: str, defect_rate: float = 0.08):
        super().__init__(name=f"Make {component_name}", defect_rate=defect_rate)
        self.component_name = component_name
        self._counter = 0
        self.failure_modes = {
            "outer_ring": ["Thermal warping", "Machining tolerance exceeded"],
            "inner_ring": ["Inner diameter too small", "Surface finish too rough"],
            "steel_balls": ["Out of roundness", "Overheated during grinding"],
            "cage": ["Stamping misalignment", "Bent retainer prong"]
        }

    def process(self, _ignored=None) -> Component:
        self._counter += 1
        self.processed += 1
        quality, reason = self._maybe_defect(self.failure_modes[self.component_name])
        part = Component(name=self.component_name, serial=self._counter, quality=quality, defect_reason=reason)
        status = f"-> {part.quality.name}" + (f" ({part.defect_reason})" if reason else "")
        self.log(f"produced {part.name}#{part.serial} {status}")
        self._sleep(0.1) 
        return part

class QualityControl(Station):
    def process(self, item: Component) -> Optional[Component]:
        self.processed += 1
        self._sleep(0.05)
        if item.quality is Quality.DEFECTIVE:
            self.rejected += 1
            self.log(f"REJECT {item.name}#{item.serial} - Reason: {item.defect_reason}")
            return None
        self.log(f"pass   {item.name}#{item.serial}")
        return item

class AssemblyStation(Station):
    def __init__(self, defect_rate: float = 0.06):
        super().__init__(name="Assembly", defect_rate=defect_rate)
        self._counter = 0

    def process(self, parts: dict) -> BallBearing:
        self._counter += 1
        self.processed += 1
        # Added part loss error handling
        quality, reason = self._maybe_defect(["Excessive friction / Binding", "Balls misaligned in cage", "Component dropped/lost during transfer"])
        bearing = BallBearing(
            serial=self._counter, outer_ring=parts["outer_ring"], inner_ring=parts["inner_ring"],
            steel_balls=parts["steel_balls"], cage=parts["cage"], quality=quality, defect_reason=reason
        )
        status = f"-> {bearing.quality.name}" + (f" ({bearing.defect_reason})" if reason else "")
        self.log(f"assembled Bearing#{bearing.serial} {status}")
        self._sleep(0.15)
        return bearing

class FinalInspection(Station):
    def process(self, bearing: BallBearing) -> Optional[BallBearing]:
        self.processed += 1
        self._sleep(0.05)
        if not bearing.is_complete() or bearing.quality is Quality.DEFECTIVE:
            self.rejected += 1
            reason = bearing.defect_reason or "Incomplete assembly"
            self.log(f"REJECT Bearing#{bearing.serial} - {reason}")
            return None
        self.log(f"pass   Bearing#{bearing.serial}")
        return bearing

class Packaging(Station):
    def __init__(self, defect_rate: float = 0.03):
        super().__init__(name="Grease & Pack", defect_rate=defect_rate)

    def process(self, bearing: BallBearing) -> Optional[BallBearing]:
        self.processed += 1
        self._sleep(0.1)
        # Added packaging fault handling
        quality, reason = self._maybe_defect(["Missing grease application", "Carton jam / Packaging destroyed", "Finished good dropped"])
        
        if quality is Quality.DEFECTIVE:
            self.rejected += 1
            bearing.quality = Quality.DEFECTIVE
            bearing.defect_reason = reason
            self.log(f"REJECT Bearing#{bearing.serial} at Packaging - {reason}")
            return None

        bearing.packaged = True
        self.log(f"greased & packaged Bearing#{bearing.serial}")
        return bearing

class ProductionLine:
    COMPONENT_NAMES = ("outer_ring", "inner_ring", "steel_balls", "cage")

    def __init__(self):
        self.makers = {n: ComponentMaker(n) for n in self.COMPONENT_NAMES}
        self.qcs = {n: QualityControl(name=f"QC {n}") for n in self.COMPONENT_NAMES}
        self.bins: dict[str, Deque[Component]] = {n: deque() for n in self.COMPONENT_NAMES}
        self.assembly = AssemblyStation()
        self.final_qc = FinalInspection(name="Final QC")
        self.packaging = Packaging()
        self.shipped: List[BallBearing] = []
        # Thread flags for E-Stop and Soft Halt
        self.run_flag = threading.Event()
        self.run_flag.set()
        self.stop_event = threading.Event()

        # Pass flags to all stations
        all_stations = [*self.makers.values(), *self.qcs.values(), self.assembly, self.final_qc, self.packaging]
        for s in all_stations:
            s.run_flag = self.run_flag
            s.stop_event = self.stop_event

    def _produce_lane(self, name: str) -> None:
        while not self.bins[name]:
            if self.stop_event.is_set(): return
            raw = self.makers[name].process()

    def _refill_bins(self) -> None:
        threads = []
        for name in self.COMPONENT_NAMES:
            t = threading.Thread(target=self._produce_lane, args=(name,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

    def _assemble_one(self) -> Optional[BallBearing]:
        for n in self.COMPONENT_NAMES:
            if not self.bins[n]:
                return Nonee
        parts = {n: self.bins[n].popleft() for n in self.COMPONENT_NAMES}
        bearing = self.assembly.process(parts)
        bearing = self.final_qc.process(bearing)
        if bearing is None:
            return None
        return self.packaging.process(bearing)

    def run(self, target: int) -> None:
        print(f"\n=== Starting parallel production: target = {target} bearings ===\n")
        while len(self.shipped) < target:
            if self.stop_event.is_set(): break
            self._refill_bins()
            if self.stop_event.is_set(): break
            bearing = self._assemble_one()

    def _report(self) -> None:
        print("\n=== Production report ===")
        all_stations: list[Station] = [*self.makers.values(), *self.qcs.values(), self.assembly, self.final_qc, self.packaging]
        for s in all_stations:
            print(f"{s.name:<20} processed={s.processed:<4} rejected={s.rejected}")
        print(f"\nShipped bearings: {len(self.shipped)}")

if __name__ == "__main__":
    random.seed(42)
    line = ProductionLine()
    
    # Run production in a background thread to keep the main thread free for controls
    prod_thread = threading.Thread(target=line.run, args=(20,), daemon=True)
    prod_thread.start()

    print("\n--- CONTROLS (Press instantly, no Enter needed): [E]=E-Stop | [R]=Resume | [S]=Soft Halt | [Q]=Quit ---\n")
    
    # Non-blocking listener loop
    while prod_thread.is_alive():
        if msvcrt.kbhit(): # Instantly checks if a key is being pressed
            key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            
            if key == 'e':
                line.run_flag.clear()
                print("\n[!] E-STOP ENGAGED - ALL MACHINERY FROZEN [!]\n")
            elif key == 'r':
                line.run_flag.set()
                print("\n[>] PRODUCTION RESUMED\n")
            elif key == 's':
                line.stop_event.set()
                line.run_flag.set() # Unfreeze in case E-Stop was active
                print("\n[i] SOFT HALT SIGNALED - FINISHING CURRENT CYCLE...\n")
            elif key == 'q':
                line.stop_event.set()
                line.run_flag.set()
                break
                
        time.sleep(0.05) # Keeps the CPU from maxing out while waiting for input

    prod_thread.join()