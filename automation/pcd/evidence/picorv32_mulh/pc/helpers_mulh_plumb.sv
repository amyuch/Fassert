/// Helper Assertion Begin
	wire h_is_mulh = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011) &&
	                 (wrapper.uut.dbg_insn_opcode[14:12] == 3'b001) &&
	                 (wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001);
	wire h_rvfi_mulh = (rvfi_insn[6:0] == 7'b0110011) &&
	                   (rvfi_insn[14:12] == 3'b001) &&
	                   (rvfi_insn[31:25] == 7'b0000001);

	reg        h_wb_seen;
	reg [31:0] h_wb_opcode;
	reg [4:0]  h_wb_rd;
	reg [31:0] h_wb_wdata;
	reg [31:0] h_wb_rs1;
	reg [31:0] h_wb_rs2;

	always @(posedge clock) begin
		if (reset) begin
			h_wb_seen   <= 1'b0;
			h_wb_opcode <= 32'd0;
			h_wb_rd     <= 5'd0;
			h_wb_wdata  <= 32'd0;
			h_wb_rs1    <= 32'd0;
			h_wb_rs2    <= 32'd0;
		end else begin
			if (rvfi_valid)
				h_wb_seen <= 1'b0;
			if (wrapper.uut.cpuregs_write && h_is_mulh) begin
				h_wb_seen   <= 1'b1;
				h_wb_opcode <= wrapper.uut.dbg_insn_opcode;
				h_wb_rd     <= wrapper.uut.latched_rd;
				h_wb_wdata  <= wrapper.uut.cpuregs_wrdata;
				h_wb_rs1    <= wrapper.uut.reg_op1;
				h_wb_rs2    <= wrapper.uut.reg_op2;
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			h_rvfi_insn_eq: assert (rvfi_insn == $past(wrapper.uut.dbg_insn_opcode));
			h_rvfi_pc_rdata_eq: assert (rvfi_pc_rdata == $past(wrapper.uut.dbg_insn_addr));
			h_rvfi_valid_eq: assert (rvfi_valid == $past((!reset) && (wrapper.uut.launch_next_insn || wrapper.uut.trap) && wrapper.uut.dbg_valid_insn));
			h_rvfi_rs1_eq: assert (!(rvfi_valid && check && h_rvfi_mulh) || rvfi_rs1_rdata == $past(wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0));
			h_rvfi_rs2_eq: assert (!(rvfi_valid && check && h_rvfi_mulh) || rvfi_rs2_rdata == $past(wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0));
			h_rvfi_rd_eq: assert (!(rvfi_valid && check && h_rvfi_mulh) || rvfi_rd_wdata ==
				($past(reset) ? 32'd0 :
				 ($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
					($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0) :
				 ($past(rvfi_valid) ? 32'd0 : $past(rvfi_rd_wdata))));
			h_rvfi_rd_addr_eq: assert (!(rvfi_valid && check && h_rvfi_mulh) || rvfi_rd_addr ==
				($past(reset) ? 5'd0 :
				 ($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
					$past(wrapper.uut.latched_rd) :
				 ($past(rvfi_valid) ? 5'd0 : $past(rvfi_rd_addr))));

			h_no_irq_on_mulh: assert (!(rvfi_valid && check && h_rvfi_mulh) || !wrapper.uut.dbg_irq_call);
			h_no_trap_on_mulh: assert (!(rvfi_valid && check && h_rvfi_mulh) || !wrapper.uut.trap);

			h_commit_rd: assert (!(wrapper.uut.cpuregs_write && h_is_mulh) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_commit_rs1: assert (!(wrapper.uut.cpuregs_write && h_is_mulh && wrapper.uut.dbg_rs1val_valid) ||
				wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1);
			h_commit_rs2: assert (!(wrapper.uut.cpuregs_write && h_is_mulh && wrapper.uut.dbg_rs2val_valid) ||
				wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2);

			h_launch_opcode: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				wrapper.uut.cpuregs_write ||
				(h_wb_seen && wrapper.uut.dbg_insn_opcode == h_wb_opcode));
			h_launch_operands: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				(wrapper.uut.cpuregs_write ?
					(wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1 &&
					 wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2) :
					(h_wb_seen && wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == h_wb_rs1 && wrapper.uut.dbg_rs2val == h_wb_rs2)));
			h_launch_rd_wdata: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				wrapper.uut.cpuregs_write ||
				(h_wb_seen && rvfi_rd_wdata == (h_wb_rd ? h_wb_wdata : 32'd0)));
			h_launch_rd_eq: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_launch_rs1_zero: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				wrapper.uut.dbg_insn_opcode[19:15] != 5'd0 || wrapper.uut.dbg_rs1val == 32'd0);
			h_launch_rs2_zero: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_mulh) ||
				wrapper.uut.dbg_insn_opcode[24:20] != 5'd0 || wrapper.uut.dbg_rs2val == 32'd0);

			h_wb_matches_retire: assert (!(rvfi_valid && check && h_rvfi_mulh) ||
				(h_wb_seen &&
				 h_wb_rd == rvfi_insn[11:7] &&
				 rvfi_rd_wdata == (h_wb_rd ? h_wb_wdata : 32'd0) &&
				 rvfi_rs1_rdata == h_wb_rs1 &&
				 rvfi_rs2_rdata == h_wb_rs2));

			h_pc_next: assert (!(rvfi_valid && check && h_rvfi_mulh) ||
				wrapper.uut.dbg_insn_addr == rvfi_pc_rdata + 32'd4);

			// Monitor invariants for the signed high product.
			// p_mul_prod == p_mul_a * p_mul_b is discharged by the PCD arithmetic node.

			// Operand/product/spec links are discharged by the PCD arithmetic node.
		end
	end
/// Helper Assertion End