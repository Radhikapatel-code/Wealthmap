pub mod scan;
pub mod filter;
pub mod sort;
pub mod fifo_match;
pub mod aggregate;

use arrow::array::RecordBatch;

pub trait Operator {
    fn execute(&self, input: Option<RecordBatch>) -> Result<RecordBatch, String>;
}
