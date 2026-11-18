	wire p_mul_is_mul =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b000) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);
	wire p_mul_ready = wrapper.uut.pcd_mul.pcpi_mul.active[1];
	wire p_mul_capture = p_mul_ready && wrapper.uut.pcd_mul.pcpi_mul.instr_mul;
	wire p_mul_wb = wrapper.uut.cpuregs_write && p_mul_is_mul;
	wire p_mul_rvfi_mul =
		(rvfi_insn[31:25] == 7'b0000001) &&
		(rvfi_insn[14:12] == 3'b000) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_mul_retire = rvfi_valid && p_mul_rvfi_mul;

	reg [31:0] p_mul_a;
	reg [31:0] p_mul_b;
	reg [31:0] p_mul_lo;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_a <= 32'd0;
			p_mul_b <= 32'd0;
			p_mul_lo <= 32'd0;
		end else if (p_mul_capture) begin
			p_mul_a <= wrapper.uut.pcd_mul.pcpi_mul.rs1[31:0];
			p_mul_b <= wrapper.uut.pcd_mul.pcpi_mul.rs2[31:0];
			p_mul_lo <= wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd;
		end
	end

	reg [31:0] p_mul_wb_word;
	reg [31:0] p_mul_wb_a;
	reg [31:0] p_mul_wb_b;
	reg [31:0] p_mul_wb_lo_snap;
	reg [4:0]  p_mul_wb_rd;
	reg        p_mul_wb_seen;
	reg        p_mul_wb_lo_ok;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_wb_word <= 32'd0;
			p_mul_wb_a <= 32'd0;
			p_mul_wb_b <= 32'd0;
			p_mul_wb_lo_snap <= 32'd0;
			p_mul_wb_rd <= 5'd0;
			p_mul_wb_seen <= 1'b0;
			p_mul_wb_lo_ok <= 1'b0;
		end else begin
			if (p_mul_wb) begin
				p_mul_wb_word <= wrapper.uut.cpuregs_wrdata;
				p_mul_wb_a <= p_mul_a;
				p_mul_wb_b <= p_mul_b;
				p_mul_wb_lo_snap <= p_mul_lo;
				p_mul_wb_rd <= wrapper.uut.latched_rd;
				p_mul_wb_seen <= 1'b1;
				p_mul_wb_lo_ok <= (wrapper.uut.cpuregs_wrdata == p_mul_lo);
			end
			if (wrapper.uut.rvfi_valid) begin
				p_mul_wb_seen <= 1'b0;
				p_mul_wb_lo_ok <= 1'b0;
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			p_trigger_eq_a: assert(p_mul_retire == checker_inst.spec_valid);

			p_mul_wb_lo_ok_inv_a: assert(!p_mul_wb_lo_ok ||
				p_mul_wb_word == p_mul_wb_lo_snap);

			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				p_mul_wb_data_a: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);

			if (p_mul_wb) begin
				p_mul_wb_from_ready_a: assert($past(p_mul_capture));
				p_mul_wb_mux_a: assert(wrapper.uut.cpuregs_wrdata == p_mul_lo);
			end

			if (checker_inst.spec_valid) begin
				p_mul_wb_seen_fact_a: assert(p_mul_wb_seen);
				p_mul_wb_lo_ok_fact_a: assert(p_mul_wb_lo_ok);
				p_mul_wb_word_fact_a: assert(wrapper.uut.rvfi_rd_wdata ==
					(p_mul_wb_rd != 5'd0 ? p_mul_wb_word : 32'd0));
				p_mul_wb_rd_fact_a: assert(wrapper.uut.rvfi_rd_addr == p_mul_wb_rd);
				p_mul_rvfi_rd_a: assert(rvfi_rd_addr == rvfi_insn[11:7]);
			end
		end
	end

	// Monitor product invariant and local cell product.
	wire p_cell_ready_p = wrapper.uut.pcd_mul.pcpi_mul.active[1];
	wire [63:0] p_cell_prod_p = $signed(wrapper.uut.pcd_mul.pcpi_mul.rs1) *
		$signed(wrapper.uut.pcd_mul.pcpi_mul.rs2);
	wire p_cell_product_p = !p_cell_ready_p ||
		(wrapper.uut.pcd_mul.pcpi_mul.rd == p_cell_prod_p);
	always @(posedge clock) begin
		if (!reset) begin
			p_cell_product: assert(p_cell_product_p);
			p_mul_reg_prod_a: assert(p_mul_lo == p_mul_a * p_mul_b);
			p_mul_wb_lo_prod_a: assert(p_mul_wb_lo_snap == p_mul_wb_a * p_mul_wb_b);
		end
	end

	// Structural cell facts for the product invariant.
	always @(posedge clock) begin
		if (!reset) begin
			if (p_mul_capture) begin
				p_mul_capture_shift_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.shift_out);
				p_mul_capture_zero_a: assert(wrapper.uut.pcd_mul.pcpi_mul.rs1[32] == 1'b0 &&
					wrapper.uut.pcd_mul.pcpi_mul.rs2[32] == 1'b0);
			end
			p_mul_active_chain_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.active[1] ||
				$past(wrapper.uut.pcd_mul.pcpi_mul.active[0]));
			p_mul_instr_stable_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.active[1] ||
				(wrapper.uut.pcd_mul.pcpi_mul.pcpi_insn == $past(wrapper.uut.pcd_mul.pcpi_mul.pcpi_insn)));
			p_mul_rs_stable_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.active[1] ||
				(wrapper.uut.pcd_mul.pcpi_mul.rs1 == $past(wrapper.uut.pcd_mul.pcpi_mul.rs1) &&
				 wrapper.uut.pcd_mul.pcpi_mul.rs2 == $past(wrapper.uut.pcd_mul.pcpi_mul.rs2)));
			p_mul_lo_sel_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.active[1] ||
				wrapper.uut.pcd_mul.pcpi_mul.shift_out ||
				(wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd == wrapper.uut.pcd_mul.pcpi_mul.rd[31:0]));
		end
	end

	// Launch snapshot: the operands and product of the launched MUL.
	reg [32:0] p_mul_launch_a;
	reg [32:0] p_mul_launch_b;
	reg        p_mul_launch_valid;
	always @(posedge clock) begin
		if (reset) begin
			p_mul_launch_a <= 33'd0;
			p_mul_launch_b <= 33'd0;
			p_mul_launch_valid <= 1'b0;
		end else if (wrapper.uut.pcd_mul.pcpi_mul.active[0] &&
		             wrapper.uut.pcd_mul.pcpi_mul.instr_mul) begin
			p_mul_launch_a <= wrapper.uut.pcd_mul.pcpi_mul.rs1;
			p_mul_launch_b <= wrapper.uut.pcd_mul.pcpi_mul.rs2;
			p_mul_launch_valid <= 1'b1;
		end else begin
			p_mul_launch_valid <= 1'b0;
		end
	end
	always @(posedge clock) begin
		if (!reset) begin
			p_mul_launch_rs_a: assert(!p_mul_launch_valid ||
				(p_mul_launch_a[31:0] == wrapper.uut.pcd_mul.pcpi_mul.rs1[31:0] &&
				 p_mul_launch_b[31:0] == wrapper.uut.pcd_mul.pcpi_mul.rs2[31:0]));
			p_mul_launch_prod_a: assert(!p_mul_launch_valid ||
				(wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd ==
				 (p_mul_launch_a[31:0] * p_mul_launch_b[31:0])));
			p_mul_capture_launch_a: assert(!p_mul_capture || p_mul_launch_valid);
		end
	end

	// Operational-operand snapshots (for the RVFI operand link).
	reg [31:0] p_mul_wb_dbg_a;
	reg [31:0] p_mul_wb_dbg_b;
	always @(posedge clock) begin
		if (reset) begin
			p_mul_wb_dbg_a <= 32'd0;
			p_mul_wb_dbg_b <= 32'd0;
		end else if (p_mul_wb) begin
			p_mul_wb_dbg_a <= wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0;
			p_mul_wb_dbg_b <= wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0;
		end
	end
	always @(posedge clock) begin
		if (!reset) begin
			if (p_mul_wb) begin
				p_mul_wb_ops_a_a: assert(p_mul_a ==
					(wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0));
				p_mul_wb_ops_b_a: assert(p_mul_b ==
					(wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0));
			end
			if (p_mul_retire) begin
				p_mul_ret_ops_dbg_a_a: assert(rvfi_rs1_rdata == p_mul_wb_dbg_a);
				p_mul_ret_ops_dbg_b_a: assert(rvfi_rs2_rdata == p_mul_wb_dbg_b);
				p_mul_ret_wb_snap_a_a: assert(p_mul_wb_a == p_mul_wb_dbg_a);
				p_mul_ret_wb_snap_b_a: assert(p_mul_wb_b == p_mul_wb_dbg_b);
				p_mul_ret_ops_zero_a: assert(
					(rvfi_insn[19:15] != 5'd0 ? rvfi_rs1_rdata : 32'd0) == p_mul_wb_a &&
					(rvfi_insn[24:20] != 5'd0 ? rvfi_rs2_rdata : 32'd0) == p_mul_wb_b);
			end
		end
	end
