/// Helper Assertion Begin
	wire p_mul_is_mulh =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b001) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);
	wire p_mul_ready = wrapper.uut.pcd_mul.pcpi_mul.active[1];
	wire p_mul_capture = p_mul_ready && wrapper.uut.pcd_mul.pcpi_mul.instr_mulh;
	wire p_mul_wb = wrapper.uut.cpuregs_write && p_mul_is_mulh;
	wire p_mul_rvfi_mulh =
		(rvfi_insn[31:25] == 7'b0000001) &&
		(rvfi_insn[14:12] == 3'b001) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_mul_retire = rvfi_valid && p_mul_rvfi_mulh;

	reg [63:0] p_mul_a;
	reg [63:0] p_mul_b;
	reg [63:0] p_mul_prod;
	reg [31:0] p_mul_hi;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_a <= 64'd0;
			p_mul_b <= 64'd0;
			p_mul_prod <= 64'd0;
			p_mul_hi <= 32'd0;
		end else if (p_mul_capture) begin
			p_mul_a <= $signed(wrapper.uut.pcd_mul.pcpi_mul.rs1);
			p_mul_b <= $signed(wrapper.uut.pcd_mul.pcpi_mul.rs2);
			p_mul_prod <= wrapper.uut.pcd_mul.pcpi_mul.rd;
			p_mul_hi <= wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd;
		end
	end

	reg [31:0] p_mul_wb_word;
	reg [63:0] p_mul_wb_a;
	reg [63:0] p_mul_wb_b;
	reg [31:0] p_mul_wb_hi_snap;
	reg [4:0]  p_mul_wb_rd;
	reg        p_mul_wb_seen;
	reg        p_mul_wb_hi_ok;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_wb_word <= 32'd0;
			p_mul_wb_a <= 64'd0;
			p_mul_wb_b <= 64'd0;
			p_mul_wb_hi_snap <= 32'd0;
			p_mul_wb_rd <= 5'd0;
			p_mul_wb_seen <= 1'b0;
			p_mul_wb_hi_ok <= 1'b0;
		end else begin
			if (p_mul_wb) begin
				p_mul_wb_word <= wrapper.uut.cpuregs_wrdata;
				p_mul_wb_a <= p_mul_a;
				p_mul_wb_b <= p_mul_b;
				p_mul_wb_hi_snap <= p_mul_hi;
				p_mul_wb_rd <= wrapper.uut.latched_rd;
				p_mul_wb_seen <= 1'b1;
				p_mul_wb_hi_ok <= (wrapper.uut.cpuregs_wrdata == p_mul_hi);
			end
			if (wrapper.uut.rvfi_valid) begin
				p_mul_wb_seen <= 1'b0;
				p_mul_wb_hi_ok <= 1'b0;
			end
		end
	end

	reg [63:0] p_mul_wb_dbg_a;
	reg [63:0] p_mul_wb_dbg_b;
	always @(posedge clock) begin
		if (reset) begin
			p_mul_wb_dbg_a <= 64'd0;
			p_mul_wb_dbg_b <= 64'd0;
		end else if (p_mul_wb) begin
			p_mul_wb_dbg_a <= wrapper.uut.dbg_rs1val_valid ?
				{{32{wrapper.uut.dbg_rs1val[31]}}, wrapper.uut.dbg_rs1val} : 64'd0;
			p_mul_wb_dbg_b <= wrapper.uut.dbg_rs2val_valid ?
				{{32{wrapper.uut.dbg_rs2val[31]}}, wrapper.uut.dbg_rs2val} : 64'd0;
		end
	end

	// PC/retirement plumbing facts (frozen pc helper group).

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


	// ------------------------------------------------------------------
	// Control/retirement monitor assertions.
	// ------------------------------------------------------------------
	always @(posedge clock) begin
		if (!reset) begin

			if (p_mul_wb) begin
				p_mul_wb_dbg_valid_a: assert(
					wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid);
				p_mul_wb_from_ready_a: assert($past(p_mul_capture));
			end

			if (p_mul_retire) begin
				p_mul_ret_seen_a: assert(p_mul_wb_seen);
				p_mul_ret_ops_dbg_a: assert(rvfi_rs1_rdata == p_mul_wb_dbg_a[31:0]);
				p_mul_ret_ops_dbg_b: assert(rvfi_rs2_rdata == p_mul_wb_dbg_b[31:0]);
				p_mul_zp_a: assert(p_mul_a == p_mul_wb_a);
				p_mul_zp_b: assert(p_mul_b == p_mul_wb_b);
				p_mul_ret_wb_snap_a: assert(p_mul_wb_a == p_mul_wb_dbg_a);
				p_mul_ret_wb_snap_b: assert(p_mul_wb_b == p_mul_wb_dbg_b);
			end

			if (p_mul_capture) begin
				p_mul_capture_shift_a: assert(wrapper.uut.pcd_mul.pcpi_mul.shift_out);
			end
		end
	end

	// MUL-style writeback facts (generic core plumbing).
	always @(posedge clock) begin
		if (!reset) begin
			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)


			if (checker_inst.spec_valid) begin
			end
		end
	end

/// Helper Assertion End
