use crate::operators::filter::Predicate;
use crate::pipeline::EnginePipeline;
use crate::schema::AggregateRecord;
use arrow::array::RecordBatch;
use sqlparser::ast::{BinaryOperator, Expr, Statement, Value};
use sqlparser::dialect::GenericDialect;
use sqlparser::parser::Parser;

pub struct SqlEngine;

impl SqlEngine {
    pub fn parse_and_execute(
        sql: &str,
        input_batch: RecordBatch,
    ) -> Result<Vec<AggregateRecord>, String> {
        let dialect = GenericDialect {};
        let ast = Parser::parse_sql(&dialect, sql).map_err(|e| e.to_string())?;

        if ast.is_empty() {
            return Err("Empty SQL query".into());
        }

        let mut predicates = Vec::new();

        if let Statement::Query(query) = &ast[0] {
            if let sqlparser::ast::SetExpr::Select(select) = query.body.as_ref() {
                if let Some(selection) = &select.selection {
                    Self::extract_predicates(selection, &mut predicates)?;
                }
            }
        }

        let pipeline = EnginePipeline::new(predicates);
        let (_, aggregates) = pipeline.run(input_batch)?;
        Ok(aggregates)
    }

    fn extract_predicates(expr: &Expr, predicates: &mut Vec<Predicate>) -> Result<(), String> {
        match expr {
            Expr::BinaryOp { left, op, right } => match op {
                BinaryOperator::Eq => {
                    if let (Expr::Identifier(ident), Expr::Value(val)) = (left.as_ref(), right.as_ref()) {
                        let col_name = ident.value.to_lowercase();
                        let val_str = match val {
                            Value::SingleQuotedString(s) | Value::DoubleQuotedString(s) => s.clone(),
                            Value::Number(n, _) => n.clone(),
                            _ => return Err("Unsupported AST value".into()),
                        };

                        let mapped_col = match col_name.as_str() {
                            "ticker" | "symbol" => "symbol".to_string(),
                            "account" | "member_id" => "member_id".to_string(),
                            "class" | "classification" => "classification".to_string(),
                            other => other.to_string(),
                        };

                        predicates.push(Predicate::Equals {
                            column: mapped_col,
                            value: val_str,
                        });
                    }
                }
                BinaryOperator::And => {
                    Self::extract_predicates(left, predicates)?;
                    Self::extract_predicates(right, predicates)?;
                }
                _ => {}
            },
            _ => {}
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::load_golden_transactions_batch;
    use std::path::PathBuf;

    fn get_testdata_dir() -> PathBuf {
        let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        p.push("testdata");
        p
    }

    #[test]
    fn test_sql_parser_frontend() {
        let testdata_dir = get_testdata_dir();
        let tx_path = testdata_dir.join("golden_transactions.json");
        let batch = load_golden_transactions_batch(&tx_path).unwrap();

        let sql = "SELECT symbol, SUM(gross_gain_inr) FROM matched_lots WHERE symbol = 'RELIANCE.NS' GROUP BY symbol";        let results = SqlEngine::parse_and_execute(sql, batch).unwrap();

        assert!(!results.is_empty());
        for r in &results {
            assert_eq!(r.symbol, "RELIANCE.NS");
        }
    }
}
