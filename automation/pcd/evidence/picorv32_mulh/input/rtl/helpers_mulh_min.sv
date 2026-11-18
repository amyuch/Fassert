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


	// Minimal retirement plumbing needed by the strict RD proof.
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
			h_wb_matches_retire: assert (!(rvfi_valid && check && h_rvfi_mulh) ||
				(h_wb_seen &&
				 h_wb_rd == rvfi_insn[11:7] &&
				 rvfi_rd_wdata == (h_wb_rd ? h_wb_wdata : 32'd0) &&
				 rvfi_rs1_rdata == h_wb_rs1 &&
				 rvfi_rs2_rdata == h_wb_rs2));

			p_trigger_eq_a: assert(p_mul_retire == checker_inst.spec_valid);


			if (p_mul_retire) begin
				p_mul_ret_ops_zero: assert(
					(rvfi_insn[19:15] != 5'd0 ?
					 {{32{rvfi_rs1_rdata[31]}}, rvfi_rs1_rdata} : 64'd0) == p_mul_wb_a &&
					(rvfi_insn[24:20] != 5'd0 ?
					 {{32{rvfi_rs2_rdata[31]}}, rvfi_rs2_rdata} : 64'd0) == p_mul_wb_b);
			end

			if (p_mul_wb) begin
				p_mul_wb_mux_a: assert(wrapper.uut.cpuregs_wrdata == p_mul_hi);
			end

			p_mul_wb_word_eq_hi_snap_a: assert(p_mul_wb_word == p_mul_wb_hi_snap);

			if (checker_inst.spec_valid) begin
				p_mul_wb_word_fact_a: assert(wrapper.uut.rvfi_rd_wdata ==
					(p_mul_wb_rd != 5'd0 ? p_mul_wb_word : 32'd0));
				p_mul_wb_rd_fact_a: assert(wrapper.uut.rvfi_rd_addr == p_mul_wb_rd);
				p_mul_rvfi_rd_a: assert(rvfi_rd_addr == rvfi_insn[11:7]);
			end

			if (p_mul_capture) begin
				p_mul_capture_shift_a: assert(wrapper.uut.pcd_mul.pcpi_mul.shift_out);
			end
			p_mul_hi_sel_a: assert(!wrapper.uut.pcd_mul.pcpi_mul.active[1] ||
				!wrapper.uut.pcd_mul.pcpi_mul.shift_out ||
				(wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd ==
				 wrapper.uut.pcd_mul.pcpi_mul.rd[63:32]));
		end
	end

	// Arithmetic monitor assertions (SMT-checked on the primary model).
	always @(posedge clock) begin
		if (!reset) begin
			p_mul_reg_prod_a: assert(p_mul_prod == p_mul_a * p_mul_b);
			p_mul_hi_cons: assert(p_mul_hi == p_mul_prod >> 32);
			p_mul_wb_hi_prod_a: assert(p_mul_wb_hi_snap ==
				(p_mul_wb_a * p_mul_wb_b) >> 32);
		end
	end
/// Helper Assertion End
