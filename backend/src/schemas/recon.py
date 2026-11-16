from pydantic import BaseModel, Field


class SourceUpload(BaseModel):
    batch_key: str = Field(min_length=2, max_length=40)
    source: str = Field(description='device 设备文件 或 console 调度台')
    source_ref: str = Field(default='', max_length=200)
    records: list[dict] = Field(min_length=1, max_length=10000)


class ResolveItem(BaseModel):
    id: int
    adopt: str = Field(description='采用来源 device / console；缺失与重复只能采用实际上报来源')
    seq: int | None = Field(default=None, description='重复差异指定采用的条目序号')


class DifferenceResolve(BaseModel):
    # 空数组或省略表示一次性采用全部挂起差异；每项指定差异 id、采用来源与重复条目序号
    items: list[ResolveItem] = Field(default_factory=list)


class ConfirmBatch(BaseModel):
    note: str = Field(default='', max_length=500)
