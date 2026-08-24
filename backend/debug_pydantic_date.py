"""Debug script para entender el comportamiento de Pydantic con date."""
from datetime import date, datetime, UTC
from typing import Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class TestModel1(BaseModel):
    my_date: Optional[date] = None


class TestModel2(BaseModel):
    my_date: date | None = None


class TestModel3(BaseModel):
    """Similar a Event pero simplificado."""
    id: str = Field(default_factory=lambda: f"event::{uuid4()}")
    type: Literal["event"] = "event"
    partition_key: str
    name: str
    date: Optional[date] = None
    deleted: bool = False


class TestModel4(BaseModel):
    """Más simple aún - sin Literal."""
    id: str
    partition_key: str
    name: str
    date: Optional[date] = None


class TestModel5(BaseModel):
    """Solo los campos necesarios."""
    partition_key: str
    name: str
    date: Optional[date] = None


class TestModel6(BaseModel):
    """Cambiar nombre del campo date a event_date."""
    partition_key: str
    name: str
    event_date: Optional[date] = None


print("=== Test 1: Optional[date] ===")
try:
    m1 = TestModel1()
    print(f"Without date: {m1.my_date}")
    m1_with_date = TestModel1(my_date=date(2026, 9, 15))
    print(f"With date: {m1_with_date.my_date}")
    print("[PASS] Test 1")
except Exception as e:
    print(f"[FAIL] Test 1: {e}")

print("\n=== Test 2: date | None ===")
try:
    m2 = TestModel2()
    print(f"Without date: {m2.my_date}")
    m2_with_date = TestModel2(my_date=date(2026, 9, 15))
    print(f"With date: {m2_with_date.my_date}")
    print("[PASS] Test 2")
except Exception as e:
    print(f"[FAIL] Test 2: {e}")

print("\n=== Test 3: Event-like model ===")
try:
    m3 = TestModel3(partition_key="test", name="Test")
    print(f"Without date: {m3.date}")
    m3_with_date = TestModel3(
        partition_key="test",
        name="Test",
        date=date(2026, 9, 15)
    )
    print(f"With date: {m3_with_date.date}")
    print("[PASS] Test 3")
except Exception as e:
    print(f"[FAIL] Test 3: {e}")

print("\n=== Test 4: No Literal ===")
try:
    m4 = TestModel4(id="test", partition_key="test", name="Test")
    print(f"Without date: {m4.date}")
    m4_with_date = TestModel4(
        id="test",
        partition_key="test",
        name="Test",
        date=date(2026, 9, 15)
    )
    print(f"With date: {m4_with_date.date}")
    print("[PASS] Test 4")
except Exception as e:
    print(f"[FAIL] Test 4: {e}")

print("\n=== Test 5: Minimal ===")
try:
    m5 = TestModel5(partition_key="test", name="Test")
    print(f"Without date: {m5.date}")
    m5_with_date = TestModel5(
        partition_key="test",
        name="Test",
        date=date(2026, 9, 15)
    )
    print(f"With date: {m5_with_date.date}")
    print("[PASS] Test 5")
except Exception as e:
    print(f"[FAIL] Test 5: {e}")

print("\n=== Test 6: Renamed field ===")
try:
    m6 = TestModel6(partition_key="test", name="Test")
    print(f"Without event_date: {m6.event_date}")
    m6_with_date = TestModel6(
        partition_key="test",
        name="Test",
        event_date=date(2026, 9, 15)
    )
    print(f"With event_date: {m6_with_date.event_date}")
    print("[PASS] Test 6")
except Exception as e:
    print(f"[FAIL] Test 6: {e}")
