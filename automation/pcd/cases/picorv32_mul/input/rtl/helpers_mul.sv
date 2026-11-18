// PCD case-local helper assertions for the MUL control/data path.
//
// These are obligations, not assumptions: the proof graph must discharge every
// named assertion before it may use the corresponding guarantee.  The names are
// deliberately local to this case and are never imported from another tree.
//
// The fast multiplier captures its operands at the start edge, registers the
// full 64-bit product, and exposes the low word at the ready edge.  The
// multiplier's own captured registers (rs1/rs2/rd) are the only sound source
// for the product relation; pcpi_rs1/pcpi_rs2 may already belong to the next
// instruction when the result is returned.

	wire p_mul_is_mul =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b000) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);
	wire p_mul_ready = wrapper.uut.pcd_mul.pcpi_mul.active[1];
	wire p_mul_capture = p_mul_ready && wrapper.uut.pcd_mul.pcpi_mul.instr_mul;

	// Ready-edge monitor.  It holds the operands, the registered 64-bit
	// product, and the low-word output until the next MUL completes.
	reg [31:0] p_mul_a;
	reg [31:0] p_mul_b;
	reg [63:0] p_mul_prod;
	reg [31:0] p_mul_lo;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_a <= 32'd0;
			p_mul_b <= 32'd0;
			p_mul_prod <= 64'd0;
			p_mul_lo <= 32'd0;
		end else if (p_mul_capture) begin
			p_mul_a <= wrapper.uut.pcd_mul.pcpi_mul.rs1[31:0];
			p_mul_b <= wrapper.uut.pcd_mul.pcpi_mul.rs2[31:0];
			p_mul_prod <= wrapper.uut.pcd_mul.pcpi_mul.rd;
			p_mul_lo <= wrapper.uut.pcd_mul.pcpi_mul.pcpi_rd;
		end
	end

	// Writeback monitor.  It mirrors the CPU's RVFI write-data registers.
	reg [31:0] p_mul_wb_word;
	reg [4:0]  p_mul_wb_rd;
	reg        p_mul_wb_seen;

	always @(posedge clock) begin
		if (reset) begin
			p_mul_wb_word <= 32'd0;
			p_mul_wb_rd <= 5'd0;
			p_mul_wb_seen <= 1'b0;
		end else begin
			if (wrapper.uut.cpuregs_write && p_mul_is_mul) begin
				p_mul_wb_word <= wrapper.uut.cpuregs_wrdata;
				p_mul_wb_rd <= wrapper.uut.latched_rd;
				p_mul_wb_seen <= 1'b1;
			end
			if (wrapper.uut.rvfi_valid)
				p_mul_wb_seen <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			if ($past(!reset) && $past(p_mul_capture))
				p_mul_reg_lo: assert(wrapper.uut.reg_out == p_mul_lo);

			// Writeback uses the captured result.
			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				p_mul_wb: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);

			if (wrapper.uut.cpuregs_write && p_mul_is_mul) begin
				p_mul_wb_from_ready: assert($past(p_mul_capture));
				p_mul_wb_lo: assert(wrapper.uut.cpuregs_wrdata == p_mul_lo);
			end

			if ($past(!reset) && $past(wrapper.uut.cpuregs_write && p_mul_is_mul)) begin
				p_mul_wb_word_copy: assert(p_mul_wb_word == $past(wrapper.uut.cpuregs_wrdata));
				p_mul_wb_word_lo: assert(p_mul_wb_word == p_mul_lo);
			end

			// At retire the writeback monitor describes the retiring MUL.
			if (checker_inst.spec_valid) begin
				p_mul_ret_word_lo: assert(p_mul_wb_word == p_mul_lo);
				p_mul_wb_seen_fact: assert(p_mul_wb_seen);
				p_mul_wb_word_fact: assert(wrapper.uut.rvfi_rd_wdata ==
					(p_mul_wb_rd != 5'd0 ? p_mul_wb_word : 32'd0));
				p_mul_wb_rd_fact: assert(wrapper.uut.rvfi_rd_addr == p_mul_wb_rd);
				p_mul_rvfi_rd: assert(rvfi_rd_addr == rvfi_insn[11:7]);
			end
		end
	end
